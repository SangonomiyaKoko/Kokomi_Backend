#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Recent 功能 - 用户 SQLite 数据库清理与完整性维护脚本

基于 data/const/recent.sql 的新数据库设计实现（顶层 user_daily_summary ->
中层 ship_index_map -> 底层 ship_index_data），替代旧的 daily_snapshot 设计。

任务流程：
  1. 扫描 SQLITE_DIR 下全部 *.db 文件，再读取 MySQL 中的"计划用户"
     （T_user_config.user_level > 0），找出未被清理的残留数据库文件；
  2. 对每个在计划列表中且存在数据库文件的用户，先获取与在线服务一致的
     Redis 分布式锁，再读取本地库必要数据；
  3. 给定一个日期 date(YYYYMMDD)：
       - 若 user_daily_summary 不存在 snapshot_date < date 的记录：
         仅执行索引完整率检查；
       - 若存在：按 顶层 -> 中层 -> 底层 删除所有不再被引用的数据，
         删除完毕后再次执行一次数据完整性检查。

删除时遵循引用安全（不会留下悬空引用）：
  - 顶层：删除 snapshot_date < date 的 user_daily_summary 记录；
  - 中层：删除不再被"保留的 summary 索引 / mode_latest_index"引用的
          ship_index_map 记录（mode 最新快照仍被引用时会被保留）；
  - 底层：删除不再被"保留的 ship_index_map.index_map / ship_latest_index"
          引用的 ship_index_data 记录。

参数效验（二次防呆）：
  1. 校验 --date 为合法的 YYYYMMDD 日历日期（拒绝如 20261399）；
  2. 计算该日期与当前服务器重置日期的差值，输出本次最多保留多少天数据；
  3. 拒绝晚于当前日期的取值；非 dry-run 时要求交互输入 y/N 二次确认，
     未确认 / 无法读取输入一律取消，绝不默认放行。

使用示例：
    python tools/cleanup.py --date 20260828
    python tools/cleanup.py --date 20260828 --dry-run
"""

import os
import sys
import json
import argparse
import logging
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import redis
import pymysql
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('recent.cleanup')

ROOT_DIR = Path(os.getcwd())

if (ROOT_DIR / 'env.dev').exists():
    load_dotenv('env.dev')
elif (ROOT_DIR / 'env.prod').exists():
    load_dotenv('env.prod')
else:
    raise FileNotFoundError('No environment file found')

# 与 recent/worker.py 中 recent_refresh_lock 使用完全相同的锁 key
LOCK_PREFIX = 'refresh_lock:recent:'
# 清理可能比单次在线刷新耗时更长，故延长锁过期时间，防止任务进行中被在线服务打断
LOCK_TTL = 300

DB_CONFIG = {
    'host': os.getenv('MYSQL_HOST', 'localhost'),
    'port': int(os.getenv('MYSQL_PORT', 3306)),
    'user': os.getenv('MYSQL_USER'),
    'password': os.getenv('MYSQL_PASSWORD'),
    'database': os.getenv('MYSQL_DATABASE'),
    'autocommit': False,
}
REDIS_CONFIG = {
    'host': os.getenv('REDIS_HOST', 'localhost'),
    'port': int(os.getenv('REDIS_PORT', 6379)),
    'db': int(os.getenv('REDIS_DATABASE', 0)),
    'password': os.getenv('REDIS_PASSWORD'),
    'decode_responses': True,
}
SQLITE_DIR = (
    Path(os.getenv('SQLITE_DIR'))
    if os.getenv('SQLITE_DIR')
    else ROOT_DIR / 'data/db'
)

# 与 recent/settings.py 口径一致：snapshot_date 使用"服务器重置日期"
# （本地时区偏移后减去重置偏移，约等于当地凌晨 5 点的自然日期）
with open(ROOT_DIR / 'data/json/init_marker.json', 'r', encoding='utf-8') as f:
    TIMEZONE = json.load(f)['timezone']
with open(ROOT_DIR / 'data/const/policy.json', 'r', encoding='utf-8') as f:
    SERVER_RESET_OFFSET = json.load(f)['SERVER_RESET_OFFSET']

# 新设计涉及的全部表
REQUIRED_TABLES = {
    'user_daily_summary',
    'mode_latest_index',
    'ship_latest_index',
    'ship_index_map',
    'ship_index_data',
    'user_recent_stats',
}

# user_daily_summary 中索引列对应的模式：约定 1-pvp 2-rank 3-clan
# 列顺序与 read_snapshot 的 SELECT 保持一致（snapshot_date 在第 0 位）
SUMMARY_MODE_COLUMNS = ((1, 1), (2, 2), (3, 3))   # (row_index, ship_mode)

# 索引列取值的约定（见 recent.sql 注释）：NULL=未记录 0=无统计数据 其他=该模式快照日期
def _is_no_index(value: Optional[int]) -> bool:
    """索引值是否表示"未记录 / 无统计数据"（NULL 或 0）"""
    return value is None or value == 0


def index_map_decode(raw: Optional[str]) -> dict:
    """反序列化 ship_index_map.index_map：`ship_id:index,...` -> {int: int}"""
    result = {}
    if not raw:
        return result
    for part in raw.split(','):
        ship_id, ship_index = part.split(':')
        result[int(ship_id)] = int(ship_index)
    return result


def date_from_int(value: int) -> Optional[date]:
    """将 YYYYMMDD 整数严格解析为日期，格式非法或日历不合法（如 20261399）返回 None"""
    text = str(value)
    if len(text) != 8:
        return None
    try:
        return datetime.strptime(text, '%Y%m%d').date()
    except ValueError:
        return None


def current_reset_date() -> int:
    """获取当前服务器重置日期（YYYYMMDD），与 Recent 服务写入 snapshot_date 的口径一致"""
    reset_timestamp = (
        int(datetime.now(timezone.utc).timestamp())
        + TIMEZONE * 3600
        - SERVER_RESET_OFFSET * 3600
    )
    return int(
        datetime.fromtimestamp(reset_timestamp, timezone.utc).strftime('%Y%m%d')
    )


# 数据读取（只读取检查/删除所必要的列）
@dataclass
class DbSnapshot:
    """一个用户库中与完整性相关的全部必要数据"""
    summaries: list = field(default_factory=list)        # (snapshot_date, pvp, rank, clan)
    mode_latest: list = field(default_factory=list)      # (ship_mode, mode_index)
    ship_latest: list = field(default_factory=list)      # (ship_mode, ship_id, data_index)
    ship_maps: list = field(default_factory=list)        # (ship_mode, ship_index, index_map)
    ship_data: list = field(default_factory=list)        # (ship_mode, ship_id, ship_index)


def read_snapshot(cursor: sqlite3.Cursor) -> DbSnapshot:
    """读取单个用户数据库的必要数据"""
    snapshot = DbSnapshot()

    cursor.execute(
        'SELECT snapshot_date, pvp_index, rank_index, clan_index '
        'FROM user_daily_summary;'
    )
    snapshot.summaries = [tuple(row) for row in cursor.fetchall()]

    cursor.execute('SELECT ship_mode, mode_index FROM mode_latest_index;')
    snapshot.mode_latest = [tuple(row) for row in cursor.fetchall()]

    cursor.execute(
        'SELECT ship_mode, ship_id, data_index FROM ship_latest_index;'
    )
    snapshot.ship_latest = [tuple(row) for row in cursor.fetchall()]

    cursor.execute(
        'SELECT ship_mode, ship_index, index_map FROM ship_index_map;'
    )
    snapshot.ship_maps = [tuple(row) for row in cursor.fetchall()]

    cursor.execute(
        'SELECT ship_mode, ship_id, ship_index FROM ship_index_data;'
    )
    snapshot.ship_data = [tuple(row) for row in cursor.fetchall()]

    return snapshot


def ensure_schema(cursor: sqlite3.Cursor) -> list:
    """检查表结构是否为新的数据库设计，返回缺失表列表"""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing = {row[0] for row in cursor.fetchall()}
    return sorted(REQUIRED_TABLES - existing)


def _summary_map_refs(summaries: list) -> tuple:
    """返回 summary 中所有索引引用。

    Returns:
        (refs, map_keys)：refs 为逐条索引引用列表 [(mode, date), ...]，
        map_keys 为去重后的引用集合。
    """
    refs = []
    map_keys = set()
    for row in summaries:
        for col_index, ship_mode in SUMMARY_MODE_COLUMNS:
            value = row[col_index]
            if _is_no_index(value):
                continue
            key = (ship_mode, int(value))
            refs.append(key)
            map_keys.add(key)
    return refs, map_keys


# 索引完整率检查
@dataclass
class CheckMetric:
    """一类完整性检查的统计结果"""
    name: str                       # 检查项名称
    checked: int = 0                # 参与检查的总量
    bad: int = 0                    # 异常数量（无法解析 / 未被引用）

    def add_bad(self, sample: str) -> None:
        self.bad += 1


@dataclass
class IntegrityResult:
    """一次完整性检查的全部指标"""
    metrics: list = field(default_factory=list)

    @property
    def is_ok(self) -> bool:
        return all(m.bad == 0 for m in self.metrics)


def run_integrity_check(snapshot: DbSnapshot) -> IntegrityResult:
    """对给定的数据库快照执行索引完整率检查。

    约定：快照中的引用都必须能解析到被引用行；存在的行也必须被引用。
    """
    result = IntegrityResult()

    # -- 顶层引用：user_daily_summary.xx_index -> ship_index_map -------
    map_key_set = {(mode, date) for mode, date, _ in snapshot.ship_maps}
    summary_refs, summary_map_keys = _summary_map_refs(snapshot.summaries)
    m1 = CheckMetric('summary->ship_map 引用')
    for mode, date in summary_refs:
        if (mode, date) not in map_key_set:
            m1.add_bad(f'summary 索引 (mode={mode}, date={date}) 无对应 ship_index_map')
    m1.checked = len(summary_refs)
    result.metrics.append(m1)

    # -- 顶层缓存引用：mode_latest_index.mode_index -> ship_index_map ----
    mode_latest_keys = set()
    m2 = CheckMetric('mode_latest->ship_map 引用')
    for ship_mode, mode_index in snapshot.mode_latest:
        if _is_no_index(mode_index):
            continue
        m2.checked += 1
        key = (int(ship_mode), int(mode_index))
        mode_latest_keys.add(key)
        if key not in map_key_set:
            m2.add_bad(f'mode_latest 索引 (mode={ship_mode}, date={mode_index}) 无对应 ship_index_map')
    result.metrics.append(m2)

    # -- 中层反向：ship_index_map 必须被顶层引用（summary / mode_latest）--
    all_refs = summary_map_keys | mode_latest_keys
    m3 = CheckMetric('ship_map 被引用')
    m3.checked = len(snapshot.ship_maps)
    for mode, date, _ in snapshot.ship_maps:
        if (mode, date) not in all_refs:
            m3.add_bad(f'ship_index_map (mode={mode}, date={date}) 未被任何记录引用')
    result.metrics.append(m3)

    # -- 中层引用：ship_index_map.index_map -> ship_index_data ---------
    ship_data_key_set = {tuple(row) for row in snapshot.ship_data}
    map_entry_keys = set()      # (mode, ship_id, index)
    m4 = CheckMetric('index_map->ship_data 引用')
    for mode, _, index_map in snapshot.ship_maps:
        for ship_id, ship_index in index_map_decode(index_map).items():
            m4.checked += 1
            key = (int(mode), int(ship_id), int(ship_index))
            map_entry_keys.add(key)
            if key not in ship_data_key_set:
                m4.add_bad(
                    f'index_map 条目 (mode={mode}, ship={ship_id}, '
                    f'index={ship_index}) 无对应 ship_index_data'
                )
    result.metrics.append(m4)

    # -- 底层缓存引用：ship_latest_index.data_index -> ship_index_data ---
    latest_keys = set()
    m5 = CheckMetric('ship_latest->ship_data 引用')
    for ship_mode, ship_id, data_index in snapshot.ship_latest:
        if _is_no_index(data_index):
            continue
        m5.checked += 1
        key = (int(ship_mode), int(ship_id), int(data_index))
        latest_keys.add(key)
        if key not in ship_data_key_set:
            m5.add_bad(
                f'ship_latest (mode={ship_mode}, ship={ship_id}, '
                f'index={data_index}) 无对应 ship_index_data'
            )
    result.metrics.append(m5)

    # -- 底层反向：ship_index_data 必须被 index_map / ship_latest 引用 -----
    ship_data_refs = map_entry_keys | latest_keys
    m6 = CheckMetric('ship_data 被引用')
    m6.checked = len(snapshot.ship_data)
    for mode, ship_id, ship_index in snapshot.ship_data:
        if (mode, ship_id, ship_index) not in ship_data_refs:
            m6.add_bad(
                f'ship_index_data (mode={mode}, ship={ship_id}, '
                f'index={ship_index}) 未被任何记录引用'
            )
    result.metrics.append(m6)

    return result


# 数据清理计划（顶层 -> 中层 -> 底层）
@dataclass
class DiscardPlan:
    """需要从数据库删除的数据清单"""
    old_dates: list = field(default_factory=list)             # summary snapshot_date 列表
    del_maps: list = field(default_factory=list)              # [(mode, date), ...]
    del_ship_data: list = field(default_factory=list)         # [(mode, ship_id, index), ...]
    kept_old_maps: list = field(default_factory=list)         # 低于 date 但被引用而保留的 map
    kept_old_ship_data: int = 0                               # 低于 date 但被引用而保留的 data


def plan_discard(snapshot: DbSnapshot, cutoff_date: int) -> DiscardPlan:
    """计算删除计划，保证删除后不会留下悬空引用。

    仅清理"不再需要"的数据：删除旧 summary 后，依次找出不再被引用的
    中层与底层记录。仍被保留层（summary / mode_latest / ship_latest /
    保留的 ship_index_map）引用的旧快照会被保留并计数。
    """
    plan = DiscardPlan()

    # ---- 顶层：需要删除的旧 summary 日期 ----
    plan.old_dates = sorted(
        {row[0] for row in snapshot.summaries if row[0] < cutoff_date}
    )

    # ---- 删除旧 summary 之后仍被保留的引用 ----
    remaining_summaries = [row for row in snapshot.summaries if row[0] >= cutoff_date]
    _, kept_summary_map_keys = _summary_map_refs(remaining_summaries)

    mode_latest_keys = {
        (int(ship_mode), int(mode_index))
        for ship_mode, mode_index in snapshot.mode_latest
        if not _is_no_index(mode_index)
    }
    retained_map_keys = kept_summary_map_keys | mode_latest_keys

    # ---- 中层：删除不再被引用的 ship_index_map ----
    for mode, date, _ in snapshot.ship_maps:
        key = (int(mode), int(date))
        if key in retained_map_keys:
            if date < cutoff_date:
                plan.kept_old_maps.append(key)
        else:
            plan.del_maps.append((mode, date))

    retained_maps = [
        row for row in snapshot.ship_maps
        if (int(row[0]), int(row[1])) in retained_map_keys
    ]

    # ---- 底层：收集仍需要保留的 ship_index_data 引用 ----
    retained_ship_data_keys = set()
    for mode, _, index_map in retained_maps:
        for ship_id, ship_index in index_map_decode(index_map).items():
            retained_ship_data_keys.add((int(mode), int(ship_id), int(ship_index)))
    for ship_mode, ship_id, data_index in snapshot.ship_latest:
        if not _is_no_index(data_index):
            retained_ship_data_keys.add((int(ship_mode), int(ship_id), int(data_index)))

    # ---- 底层：删除不再被引用的 ship_index_data ----
    for mode, ship_id, ship_index in snapshot.ship_data:
        key = (int(mode), int(ship_id), int(ship_index))
        if key in retained_ship_data_keys:
            if ship_index < cutoff_date:
                plan.kept_old_ship_data += 1
        else:
            plan.del_ship_data.append((mode, ship_id, ship_index))

    return plan


def simulate_discard(snapshot: DbSnapshot, plan: DiscardPlan) -> DbSnapshot:
    """在内存中模拟执行删除计划后的数据库快照（供 dry-run 使用）"""
    del_dates = set(plan.old_dates)
    del_map_keys = set(plan.del_maps)
    del_ship_data_keys = set(plan.del_ship_data)

    post = DbSnapshot()
    post.summaries = [r for r in snapshot.summaries if r[0] not in del_dates]
    post.mode_latest = list(snapshot.mode_latest)   # mode_latest_index 永不删除
    post.ship_latest = list(snapshot.ship_latest)   # ship_latest_index 永不删除
    post.ship_maps = [
        r for r in snapshot.ship_maps if (r[0], r[1]) not in del_map_keys
    ]
    post.ship_data = [
        r for r in snapshot.ship_data if tuple(r) not in del_ship_data_keys
    ]
    return post


# 单用户处理
def _delete_summaries(cursor, old_dates: list) -> None:
    cursor.executemany(
        'DELETE FROM user_daily_summary WHERE snapshot_date = ?;',
        [[date] for date in old_dates],
    )


def _delete_ship_maps(cursor, del_maps: list) -> None:
    cursor.executemany(
        'DELETE FROM ship_index_map WHERE ship_mode = ? AND ship_index = ?;',
        [list(item) for item in del_maps],
    )


def _delete_ship_data(cursor, del_ship_data: list) -> None:
    cursor.executemany(
        'DELETE FROM ship_index_data '
        'WHERE ship_mode = ? AND ship_id = ? AND ship_index = ?;',
        [list(item) for item in del_ship_data],
    )


def _fmt_rate(metric: CheckMetric) -> str:
    """格式化单个检查项的完整率"""
    if metric.checked == 0:
        return f'{metric.name} - (0)'
    rate = (metric.checked - metric.bad) / metric.checked * 100
    return f'{metric.name} {rate:.1f}% ({metric.checked - metric.bad}/{metric.checked})'


def log_integrity(account_id: int, result: IntegrityResult, stage: str) -> None:
    """输出一次完整性检查的结果"""
    if result.is_ok:
        logger.info(
            '%s | [%s] 索引完整率通过: %s',
            account_id, stage,
            ' '.join(_fmt_rate(m) for m in result.metrics),
        )
    else:
        logger.warning(
            '%s | [%s] 索引完整率存在异常: %s',
            account_id, stage,
            ' '.join(_fmt_rate(m) for m in result.metrics),
        )
        for metric in result.metrics:
            if not metric.bad:
                continue
            logger.warning(
                '%s | [%s] 检查项 <%s> 异常 %d 处',
                account_id, stage, metric.name, metric.bad,
            )
            for sample in metric.samples:
                logger.warning('%s | [%s]   - %s', account_id, stage, sample)


def process_user(
    account_id: int,
    db_path: Path,
    cutoff_date: int,
    redis_client,
    dry_run: bool,
) -> tuple:
    """在分布式锁保护下处理单个用户。

    Returns:
        (status, deleted)：状态码及本次删除的记录数量 dict。
        状态码: NO_FILE / EMPTY / CHECK_OK / CHECK_ISSUE /
                CLEAN_OK / CLEAN_ISSUE / SKIP / BAD_SCHEMA / ERROR
        deleted: {'summary': n, 'map': n, 'ship_data': n}，仅在真正执行了
                 删除（非 dry-run 且清理分支）时包含实际值。
    """
    lock_key = f'{LOCK_PREFIX}{account_id}'
    acquired = redis_client.set(lock_key, 1, nx=True, ex=LOCK_TTL)
    if not acquired:
        logger.warning('%s | 获取分布式锁失败，跳过', account_id)
        return 'SKIP', {}

    try:
        if not db_path.exists():
            return 'NO_FILE', {}

        conn = sqlite3.connect(str(db_path), timeout=15, isolation_level=None)
        try:
            cursor = conn.cursor()
            cursor.execute('PRAGMA busy_timeout = 15000;')

            missing = ensure_schema(cursor)
            if missing:
                logger.error(
                    '%s | 数据库不是新设计（缺少表 %s），跳过',
                    account_id, missing,
                )
                return 'BAD_SCHEMA', {}

            snapshot = read_snapshot(cursor)
            if not snapshot.summaries:
                logger.info('%s | user_daily_summary 为空，无需处理', account_id)
                return 'EMPTY', {}

            # 判断是否存在需要抛弃的旧快照数据
            old_dates = [d for d, *_ in snapshot.summaries if d < cutoff_date]
            if not old_dates:
                result = run_integrity_check(snapshot)
                log_integrity(account_id, result, '检查')
                status = 'CHECK_OK' if result.is_ok else 'CHECK_ISSUE'
                return status, {}

            # 存在旧数据，按 顶层 -> 中层 -> 底层 计算删除计划
            plan = plan_discard(snapshot, cutoff_date)
            logger.info(
                '%s | 存在 %d 个早于 %d 的快照，计划删除: summary %d / '
                'ship_index_map %d / ship_index_data %d',
                account_id, len(old_dates), cutoff_date,
                len(plan.old_dates), len(plan.del_maps), len(plan.del_ship_data),
            )
            if plan.kept_old_maps or plan.kept_old_ship_data:
                logger.info(
                    '%s | 其中 %d 个 ship_index_map / %d 条 ship_index_data 低于该日期 '
                    '但仍被现有记录引用，予以保留',
                    account_id, len(plan.kept_old_maps), plan.kept_old_ship_data,
                )

            if dry_run:
                logger.info('%s | [dry-run] 未执行任何删除操作', account_id)
                deleted = {}
                # 在内存中模拟删除后的状态，用于预测最终完整性检查结果
                snapshot = simulate_discard(snapshot, plan)
                stage = '清理后(dry-run)'
            else:
                deleted = {
                    'summary': len(plan.old_dates),
                    'map': len(plan.del_maps),
                    'ship_data': len(plan.del_ship_data),
                }
                cursor.execute('BEGIN IMMEDIATE')
                _delete_summaries(cursor, plan.old_dates)
                _delete_ship_maps(cursor, plan.del_maps)
                _delete_ship_data(cursor, plan.del_ship_data)
                cursor.execute('COMMIT')
                snapshot = read_snapshot(cursor)
                stage = '清理后'

            if not snapshot.summaries:
                logger.warning(
                    '%s | 清理后 user_daily_summary 已无记录，但 mode_latest_index / '
                    'ship_latest_index 缓存可能仍然存在，在线服务将判定为数据不完整',
                    account_id,
                )
            elif len(snapshot.summaries) == 1:
                logger.warning(
                    '%s | 清理后 user_daily_summary 仅剩 1 条记录，在线服务将判定为数据不完整',
                    account_id,
                )

            # 删除完毕后执行最终完整性检查
            result = run_integrity_check(snapshot)
            log_integrity(account_id, result, stage)
            status = 'CLEAN_OK' if result.is_ok else 'CLEAN_ISSUE'
            return status, deleted

        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.error('%s | SQLite 操作失败: %s', account_id, e)
        return 'ERROR', {}
    except Exception as e:
        logger.error('%s | 处理失败: %s: %s', account_id, type(e).__name__, e)
        return 'ERROR', {}
    finally:
        redis_client.delete(lock_key)


# 入口
def fetch_planned_user_ids(cursor) -> set:
    """读取所有 Recent 计划更新用户的 account_id（与 worker 的列表一致）"""
    sql = """
        SELECT account_id
        FROM T_user_config
        WHERE user_level > 0;
    """
    cursor.execute(sql)
    return {int(row[0]) for row in cursor.fetchall()}


def collect_sqlite_files() -> tuple:
    """扫描 SQLITE_DIR 下的 *.db 文件。

    Returns:
        (user_files, invalid_files)：
        user_files  为 {account_id: Path}，仅包含以纯数字命名的文件；
        invalid_files 为不符合命名规范的文件路径列表。
    """
    user_files = {}
    invalid_files = []
    if not SQLITE_DIR.exists():
        logger.warning('SQLite 目录不存在: %s', SQLITE_DIR)
        return user_files, invalid_files

    for path in SQLITE_DIR.glob('*.db'):
        stem = path.stem
        if stem.isdigit():
            user_files[int(stem)] = path
        else:
            invalid_files.append(str(path))
    return user_files, invalid_files


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Recent 用户数据库清理与完整性维护脚本',
    )
    parser.add_argument(
        '--date', type=int, required=True,
        help='快照保留日期（YYYYMMDD），早于该日期的旧快照数据将被清理',
    )
    parser.add_argument(
        '--dry-run', action='store_true',
        help='仅计算并打印将要删除的数据，不实际执行删除',
    )
    args = parser.parse_args()

    # ---- 参数效验（该操作不可逆，必须严格校验后再继续）-----------------
    cutoff_value = args.date
    cutoff_day = date_from_int(cutoff_value)
    if cutoff_day is None:
        parser.error(
            f'--date 不是合法日期（YYYYMMDD 格式的整数，例如 20260828），'
            f'实际传入: {cutoff_value}'
        )

    today_value = current_reset_date()
    today_day = date_from_int(today_value)
    if today_day is None:  # 理论上不会发生，防御性处理
        parser.error(f'无法计算当前重置日期: {today_value}')
    logger.info(
        '清理截止日期: %d | 当前服务器重置日期: %d | dry-run: %s',
        cutoff_value, today_value, args.dry_run,
    )

    # 最多保留 = 截止日期到当前日期之间的自然日数量（含两端）
    retained_days = (today_day - cutoff_day).days + 1
    if retained_days < 1:
        parser.error(
            f'--date {cutoff_value} 晚于当前重置日期 {today_value}，'
            f'操作将删除当前全部数据且不可逆，已拒绝执行'
        )
    logger.info(
        '本次操作最多将保留 %d 天的快照数据'
        '（仅清理早于 %d 的数据，当前日期 %d）',
        retained_days, cutoff_value, today_value,
    )

    # 二次确认，防止人为输入错误导致不可逆删除（dry-run 不会真正删除，跳过确认）
    if args.dry_run:
        logger.info('dry-run 模式，跳过二次确认')
    else:
        try:
            answer = input(
                f'该操作不可逆，将删除早于 {cutoff_value} 的所有快照数据，'
                f'最多保留 {retained_days} 天。是否继续? [y/N]: '
            ).strip().lower()
        except EOFError:
            # 非交互环境下读取不到输入，按"未确认"处理，绝不默认放行
            answer = ''
        if answer not in ('y', 'yes'):
            logger.info('未确认（收到 %r），操作已取消', answer)
            return
        logger.info('已确认，继续执行清理操作')

    mysql_conn = pymysql.connect(**DB_CONFIG)
    redis_client = redis.Redis(**REDIS_CONFIG)

    counters = {
        'planned': 0, 'leftover': 0, 'no_file': 0, 'empty': 0,
        'check_ok': 0, 'check_issue': 0, 'clean_ok': 0, 'clean_issue': 0,
        'skip': 0, 'bad_schema': 0, 'error': 0,
        'del_summary': 0, 'del_map': 0, 'del_ship_data': 0,
    }

    try:
        # 1. 先扫描磁盘上的全部 .db 文件，再读取 MySQL 中的计划用户
        user_files, invalid_files = collect_sqlite_files()
        for path in invalid_files:
            logger.warning('忽略不符合命名规范的数据库文件: %s', path)
        logger.info('磁盘数据库文件数量: %d', len(user_files))

        with mysql_conn.cursor() as cursor:
            planned_ids = fetch_planned_user_ids(cursor)
        logger.info('MySQL 计划用户数量: %d', len(planned_ids))

        # 2. 查找未被清理的残留数据库文件（磁盘存在但 MySQL 中已无对应计划用户）
        file_ids = set(user_files)
        leftover_ids = sorted(file_ids - planned_ids)
        counters['leftover'] = len(leftover_ids)
        if leftover_ids:
            logger.warning(
                '发现 %d 个未删除的数据库文件（MySQL 中已无对应计划用户）: %s',
                len(leftover_ids), leftover_ids,
            )
        else:
            logger.info('未发现残留的数据库文件')

        # 3. 逐个处理仍在计划中的用户
        task_ids = sorted(file_ids & planned_ids)
        counters['planned'] = len(task_ids)
        logger.info('本次待处理用户数量: %d', len(task_ids))

        for index, account_id in enumerate(task_ids, 1):
            logger.info('=' * 70)
            logger.info('[%d/%d] 处理用户 %s', index, len(task_ids), account_id)
            status, deleted = process_user(
                account_id, user_files[account_id], cutoff_value,
                redis_client, args.dry_run,
            )
            if status in counters:
                counters[status] += 1
            else:
                counters['error'] += 1

            if status.endswith('_ISSUE'):
                logger.warning('%s | 完整性检查未通过，请关注上方异常明细', account_id)
            # 仅在真正执行删除时累加删除量
            if status in ('CLEAN_OK', 'CLEAN_ISSUE') and deleted:
                counters['del_summary'] += deleted['summary']
                counters['del_map'] += deleted['map']
                counters['del_ship_data'] += deleted['ship_data']

        # 4. 输出汇总
        logger.info('=' * 70)
        issue_total = counters['check_issue'] + counters['clean_issue']
        logger.info(
            '清理完成汇总: 计划 %d | 残留文件 %d | 无文件 %d | 空库 %d | '
            '仅检查通过 %d | 仅检查异常 %d | 已清理 %d | 清理后异常 %d | '
            '存在异常合计 %d | 跳锁 %d | 旧结构 %d | 出错 %d',
            counters['planned'], counters['leftover'], counters['no_file'],
            counters['empty'], counters['check_ok'], counters['check_issue'],
            counters['clean_ok'], counters['clean_issue'], issue_total,
            counters['skip'], counters['bad_schema'], counters['error'],
        )
        if not args.dry_run:
            logger.info(
                '已删除记录: user_daily_summary %d | ship_index_map %d | '
                'ship_index_data %d',
                counters['del_summary'], counters['del_map'], counters['del_ship_data'],
            )
        else:
            logger.info('dry-run 模式，未删除任何记录')
    finally:
        if mysql_conn:
            mysql_conn.close()
        if redis_client:
            redis_client.close()


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logger.info('Interrupted by user')
        sys.exit(1)
