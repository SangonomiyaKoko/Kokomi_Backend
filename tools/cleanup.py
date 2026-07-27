import os
import json
import redis
import sqlite3
import logging
import pymysql
from tqdm import tqdm
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(os.getcwd())

if (ROOT_DIR / 'env.dev').exists():
    load_dotenv('env.dev')
elif (ROOT_DIR / 'env.prod').exists():
    load_dotenv('env.prod')
else:
    raise FileNotFoundError('No environment file found')

DB_CONFIG = {
    "host": os.getenv("MYSQL_HOST", "localhost"),
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "autocommit": False
}
REDIS_CONFIG = {
    "host": os.getenv("REDIS_HOST", "localhost"),
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DATABASE", 0)),
    "password": os.getenv("REDIS_PASSWORD"),
    "decode_responses": True
}

SQLITE_DIR = Path(os.getenv("SQLITE_DIR", ROOT_DIR / 'data/db'))

with open(ROOT_DIR / 'data/json/init_marker.json', 'r', encoding='utf-8') as f:
    _marker = json.load(f)
    TIMEZOEN: int = _marker['timezone']

with open(ROOT_DIR / 'data/const/policy.json', 'r', encoding='utf-8') as f:
    _policy = json.load(f)
    SERVER_RESET_OFFSET: int = _policy['SERVER_RESET_OFFSET']


class DailySummaryRow:
    """user_daily_summary 的一行数据（脚本内联版本，避免依赖项目包）。"""

    __slots__ = ('is_public', 'total_battles', 'pve_battles',
                 'pvp_battles', 'ranked_battles', 'karma',
                 'index_table', 'updated_at')

    def __init__(self, is_public, total_battles, pve_battles,
                 pvp_battles, ranked_battles, karma,
                 index_table, updated_at):
        self.is_public = bool(is_public)
        self.total_battles = total_battles
        self.pve_battles = pve_battles
        self.pvp_battles = pvp_battles
        self.ranked_battles = ranked_battles
        self.karma = karma
        self.index_table = index_table
        self.updated_at = updated_at

    @classmethod
    def from_row(cls, row):
        return cls(
            is_public=row[0], total_battles=row[1], pve_battles=row[2],
            pvp_battles=row[3], ranked_battles=row[4], karma=row[5],
            index_table=row[6], updated_at=row[7],
        )


def _ship_map_decode(data: str) -> dict[int, int]:
    """解析 snapshot_index 中 ship_map 字段的编码字符串。"""
    result = {}
    if not data:
        return result
    for f in data.split(','):
        k, v = f.split(':', 1)
        result[int(k)] = int(v)
    return result


def _get_reset_date_list(current_timestamp: int, start_date: int) -> list[int]:
    """生成从 start_date 到当前日期的连续日期列表（YYYYMMDD 整数）。"""
    from datetime import datetime, timezone
    result = []
    for _ in range(1000):
        reset_ts = current_timestamp + TIMEZOEN * 3600 - SERVER_RESET_OFFSET * 3600
        date_int = int(datetime.fromtimestamp(reset_ts, timezone.utc).strftime("%Y%m%d"))
        result.append(date_int)
        if date_int == start_date:
            break
        current_timestamp -= 86400
    result.reverse()
    return result


def read_all_user_limits(cursor) -> dict[int, int]:
    """从 MySQL 读取所有启用用户的 account_id 与 storage_limit"""
    sql = """
        SELECT 
            account_id, 
            storage_limit
        FROM T_user_config
        WHERE user_level > 0 
          AND storage_limit > 0;
    """
    cursor.execute(sql)
    return {row[0]: row[1] for row in cursor.fetchall()}


def load_daily_summaries(db_path: Path) -> dict[int, DailySummaryRow]:
    """从 SQLite 加载 user_daily_summary 全部记录"""
    if not db_path.exists():
        return {}

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        sql = """
            SELECT
                is_public, total_battles, pve_battles,
                pvp_battles, ranked_battles, karma,
                index_table, updated_at, snapshot_date
            FROM user_daily_summary
            ORDER BY snapshot_date;
        """
        cursor.execute(sql)
        result = {}
        for row in cursor.fetchall():
            result[int(row[9])] = DailySummaryRow.from_row(row[:8])
        return result


def cleanup_one_user(
    account_id: int, storage_limit: int, current_timestamp: int, redis_client
) -> tuple[int, int, int]:
    """清理单个用户的过期数据。

    Returns:
        (deleted_summaries, deleted_indexes, deleted_snapshots)
    """
    db_path = SQLITE_DIR / f'{account_id}.db'

    if not db_path.exists():
        return 0, 0, 0

    daily_summary = load_daily_summaries(db_path)
    if not daily_summary:
        return 0, 0, 0

    summary_date_list = _get_reset_date_list(
        current_timestamp, min(daily_summary.keys())
    )

    if len(summary_date_list) <= storage_limit + 1:
        return 0, 0, 0

    lock_key = f"refresh_lock:recent:{account_id}"
    acquired = redis_client.set(lock_key, 1, nx=True, ex=60)
    if not acquired:
        logger.warning(f'{account_id} | Failed to acquire lock, skipping')
        return 0, 0, 0

    try:
        keep_dates = summary_date_list[-(storage_limit + 1):]
        delete_dates = summary_date_list[:-(storage_limit + 1)]

        keep_indexes: set[str] = set()
        for d in keep_dates:
            s = daily_summary.get(d)
            if s is not None and s.index_table is not None:
                keep_indexes.add(s.index_table)

        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()

            cursor.execute("SELECT snapshot_date, ship_map FROM daily_snapshot_index;")
            index_rows = cursor.fetchall()

            delete_indexes: list[str] = []
            keep_snapshots: set[tuple[int, int]] = set()

            for row in index_rows:
                idx = row[0]
                ship_map = _ship_map_decode(row[1])
                if idx not in keep_indexes:
                    delete_indexes.append(idx)
                else:
                    for ship_id, ship_date in ship_map.items():
                        keep_snapshots.add((ship_id, ship_date))

            cursor.execute("SELECT ship_id, snapshot_date FROM ship_latest_cache;")
            for row in cursor.fetchall():
                keep_snapshots.add((row[0], row[1]))

            cursor.execute("SELECT ship_id, snapshot_date FROM ship_daily_snapshot;")
            all_snapshot_keys = [(row[0], row[1]) for row in cursor.fetchall()]
            delete_snapshots = [k for k in all_snapshot_keys if k not in keep_snapshots]

            cursor.execute(
                "DELETE FROM user_recent_stats "
                "WHERE strftime('%s', 'now') - strftime('%s', created_at) > ? * 86400",
                [storage_limit],
            )

            if delete_dates:
                cursor.executemany(
                    "DELETE FROM user_daily_summary WHERE snapshot_date = ?;",
                    [[d] for d in delete_dates],
                )

            if delete_indexes:
                cursor.executemany(
                    "DELETE FROM daily_snapshot_index WHERE snapshot_date = ?;",
                    [[d] for d in delete_indexes],
                )

            if delete_snapshots:
                cursor.executemany(
                    "DELETE FROM ship_daily_snapshot "
                    "WHERE ship_id = ? AND snapshot_date = ?;",
                    delete_snapshots,
                )

            cursor.execute("VACUUM;")
            conn.commit()

            return len(delete_dates), len(delete_indexes), len(delete_snapshots)
    finally:
        redis_client.delete(lock_key)


def main():
    current_timestamp = int(datetime.now(timezone.utc).timestamp())

    mysql_conn = pymysql.connect(**DB_CONFIG)
    redis_client = redis.Redis(**REDIS_CONFIG)

    try:
        with mysql_conn.cursor() as cursor:
            user_limits = read_all_user_limits(cursor)

        if not user_limits:
            logger.info('No users to clean up')
            return

        total_deleted_summaries = 0
        total_deleted_indexes = 0
        total_deleted_snapshots = 0
        cleaned_users = 0

        with tqdm(
            total=len(user_limits),
            desc="Cleaning up user databases",
            unit="user",
        ) as pbar:
            for account_id, storage_limit in user_limits.items():
                try:
                    d_sum, d_idx, d_snap = cleanup_one_user(
                        account_id, storage_limit, current_timestamp, redis_client
                    )

                    if d_sum > 0:
                        cleaned_users += 1
                        total_deleted_summaries += d_sum
                        total_deleted_indexes += d_idx
                        total_deleted_snapshots += d_snap
                        pbar.set_postfix_str(
                            f'User {account_id}: {d_sum}/{d_idx}/{d_snap}'
                        )
                        logger.info(
                            f'{account_id} | Delete row: '
                            f'{d_sum} / {d_idx} / {d_snap}'
                        )
                except Exception as e:
                    logger.error(
                        f'{account_id} | Cleanup failed: {type(e).__name__}'
                    )
                finally:
                    pbar.update()

        logger.info(
            f'Cleanup complete: {cleaned_users} users, '
            f'{total_deleted_summaries} summaries, '
            f'{total_deleted_indexes} indexes, '
            f'{total_deleted_snapshots} snapshots deleted'
        )

    finally:
        if mysql_conn:
            mysql_conn.close()
        if redis_client:
            redis_client.close()


if __name__ == '__main__':
    """用户数据库过期数据清理脚本。

    清理超出 storage_limit + 1 的 daily_summary 及其级联数据。
    使用与 worker 相同的 Redis 分布式锁，可与在线服务安全共存。

    每个用户仅在确认需要清理后才获取锁，避免不必要的锁竞争。

    使用示例：
    python tools/cleanup.py
    """
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
