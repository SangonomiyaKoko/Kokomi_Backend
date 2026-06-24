import sqlite3
import traceback
from sqlite3 import Cursor
from typing import Optional
from pathlib import Path
from typing_extensions import TypedDict

from logger import logger
from exception import write_exception
from utils import get_reset_date, get_reset_date_list
from settings import SQLITE_DIR, CREATE_SQL

class UserStats(TypedDict):
    is_public: bool
    total_battles: int
    pve_battles: int
    pvp_battles: int
    ranked_battles: int
    karma: int

HIDDEN_USER_STATS = UserStats(
    is_public=False,
    total_battles=0,
    pve_battles=0,
    pvp_battles=0,
    ranked_battles=0,
    karma=0
)

class UserUpdater:
    """负责维护用户的近期数据库文件，并检查用户是否需要更新"""
    @staticmethod
    def _ship_map_decode(data: str):
        fields = data.split('1')
        result = {}
        for f in fields:
            k, v = f.split(':', 1)
            result[int(k)] = int(v)
        return result
    
    @staticmethod
    def _init_new_database(account_id: int, db_path: Path) -> bool:
        """初始化数据库文件，初始化成功返回是否成功初始化文件"""
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()

                # 初始化数据库
                cursor.executescript(CREATE_SQL)

                conn.commit()
                return True
        except Exception as e:
            error_name = type(e).__name__
            logger.error(f'{account_id} | SQLite3 initialization error')
            write_exception(
                error_type="DatabaseError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            if db_path.exists():
                db_path.unlink(missing_ok=True)
                logger.warning(f"Corrupted database file deleted: {db_path}")
            return False

    @staticmethod
    def _read_all_daily_summary(cursor: Cursor) -> dict:
        result = {}
        sql = """
            SELECT 
                snapshot_date, 
                is_public, 
                total_battles, 
                pve_battles, 
                pvp_battles, 
                ranked_battles, 
                karma, 
                index_table, 
                updated_at
            FROM user_daily_summary 
            ORDER BY snapshot_date;
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        for row in rows:
            result[row[0]] = row[1:]
        return result

    @staticmethod
    def _insert_daily_summary(cursor: Cursor, summary_date: int, summary_row: list):
        sql = """
            INSERT INTO user_daily_summary (
                snapshot_date,
                is_public,
                total_battles,
                pve_battles,
                pvp_battles,
                ranked_battles,
                karma,
                index_table,
                updated_at
            ) VALUES (
                ?,?,?,?,?,?,?,?,?
            );
        """
        cursor.execute(sql, [summary_date] + summary_row)

    @staticmethod
    def _update_daily_summary(
        cursor: Cursor, 
        snapshot_date: int, 
        summary_data: UserStats, 
        index_table: Optional[str], 
        update_time: int
    ):
        sql = """
            UPDATE user_daily_summary 
            SET
                is_public = ?,
                total_battles = ?,
                pve_battles = ?, 
                pvp_battles = ?, 
                ranked_battles = ?, 
                karma = ?, 
                index_table = ?,
                updated_at = ?
            WHERE snapshot_date = ?;
        """
        cursor.execute(sql, [
            summary_data['is_public'],
            summary_data['total_battles'],
            summary_data['pve_battles'],
            summary_data['pvp_battles'],
            summary_data['ranked_battles'],
            summary_data['karma'],
            index_table,
            update_time,
            snapshot_date
        ])

    @staticmethod
    def clean_up(cursor: Cursor, account_id: int, user_limit: int, summary_date_list: list, daily_summary: dict):
        # 更新保留的日期列表（保留最近 user_limit 条）
        keep_summary_list = summary_date_list[-user_limit:]
        # 需要删除的 summary_date
        deleted_summary_list = summary_date_list[:-user_limit]

        # 构建需要保留的 snapshot_index 集合
        keep_index_set = set()
        for summary_date in keep_summary_list:
            if summary_date not in daily_summary:
                continue
            if daily_summary[summary_date][6] is None:  # index_table 字段索引为6
                continue
            keep_index_set.add(daily_summary[summary_date][6])
        
        # 所有的 snapshot_index 集合
        snapshot_index = {}
        cursor.execute("SELECT snapshot_date, ship_map FROM daily_snapshot_index;")
        rows = cursor.fetchall()
        for row in rows:
            if not row[1]:
                snapshot_index[row[0]] = {}

            fields = row[0].split(',')
            ship_map = {}
            for f in fields:
                k, v = f.split(':', 1)
                ship_map[int(k)] = int(v)
            snapshot_index[row[0]] = ship_map

        # 需要删除的 snapshot_index
        deleted_index_list = []
        # 构建需要保留的 ship_snapshot 集合
        keep_snapshot_set = set()
        for index, data in snapshot_index.items():
            if index not in keep_index_set:
                deleted_index_list.append(index)
            else:
                # 记录被引用的 ship_snapshot 索引，使用元组(ship_id, ship_date)
                for ship_id, ship_date in data.items():
                    keep_snapshot_set.add((ship_id, ship_date))
        
        # 读取 ship_latest_cache 中引用的 ship_snapshot
        latest_ship_cache = {}
        cursor.execute("SELECT ship_id, snapshot_date FROM ship_latest_cache;")
        rows = cursor.fetchall()
        for row in rows:
            latest_ship_cache[row[0]] = row[1]
        for ship_id, ship_date in latest_ship_cache.items():
            keep_snapshot_set.add((ship_id, ship_date))

        # 所有的 ship_snapshot 集合
        ship_snapshot = {}
        cursor.execute("SELECT ship_id, snapshot_date FROM ship_daily_snapshot;")
        rows = cursor.fetchall()
        for row in rows:
            ship_snapshot[row[0]] = row[1]

        # 需要删除的 ship_snapshot
        deleted_snapshot_list = []
        for ship_id, ship_date in ship_snapshot.items():
            if (ship_id, ship_date) not in keep_snapshot_set:
                deleted_snapshot_list.append((ship_id, ship_date))
        
        # 执行数据库操作
        cursor.executemany("DELETE FROM user_daily_summary WHERE snapshot_date = ?;", deleted_summary_list)
        cursor.executemany("DELETE FROM daily_snapshot_index WHERE snapshot_date = ?;", deleted_index_list)
        cursor.executemany("DELETE FROM ship_daily_snapshot WHERE ship_id = ? AND snapshot_date = ?;", deleted_snapshot_list)
        cursor.execute("VACUUM;")
        logger.info(f'{account_id} | Delete row: {len(deleted_summary_list)} / {len(deleted_index_list)} / {len(deleted_snapshot_list)}')

    @classmethod
    def main(
        cls,
        account_id: int, 
        user_limit: int,
        current_timestamp: int,
        user_latest_stats: Optional[UserStats],
        user_update_time: Optional[int]
    ) -> bool:
        db_path = SQLITE_DIR / f'{account_id}.db'
        
        # 用户数据库文件不存在，执行初始化数据库文件
        if not db_path.exists():
            if not cls._init_new_database(account_id, db_path):
                return False
                
        # 主数据库中不存在该用户的数据
        if user_latest_stats is None:
            return True
        
        try:
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                daily_summary = cls._read_all_daily_summary(cursor)

                # 新数据库文件（无任何 daily_summary 记录）
                if daily_summary == {}:
                    summary_date_list = []
                else:
                    # 获取连续的时间列表
                    summary_date_list = get_reset_date_list(current_timestamp, min(daily_summary.keys()))

                # 删除超出储存限制的记录(每10天删除一次)
                if len(summary_date_list) >= user_limit + 10:
                    cls.clean_up(
                        cursor=cursor,
                        account_id=account_id,
                        user_limit=user_limit,
                        summary_date_list=summary_date_list,
                        daily_summary=daily_summary
                    )
                    conn.commit()
                
                # 校验数据库完整性（补全缺失日期的记录）
                last_summary_date = None
                for summary_date in summary_date_list:
                    if summary_date in daily_summary:
                        last_summary_date = summary_date
                        continue
                    
                    # 获取不到修复数据，理论上 last_summary_date 不会为None
                    if last_summary_date is None:
                        logger.warning(f'{account_id} | Fix row {summary_date} failed')
                        continue

                    # 缺失某个日期的数据
                    cls._insert_daily_summary(cursor, summary_date, list(daily_summary[last_summary_date]))
                    conn.commit()

                # 用户没有 daily_summary 数据
                if last_summary_date is None:
                    if not user_latest_stats['is_public']:
                        cls._insert_daily_summary(cursor, get_reset_date(current_timestamp - 86400), [0]*6 + [None, user_update_time])
                        cls._insert_daily_summary(cursor, get_reset_date(current_timestamp), [0]*6 + [None, user_update_time])
                        conn.commit()
                        return False
                    elif user_latest_stats['pvp_battles'] + user_latest_stats['ranked_battles'] == 0:
                        cls._insert_daily_summary(
                            cursor, 
                            get_reset_date(current_timestamp - 86400), 
                            [1, user_latest_stats['total_battles'], user_latest_stats['pve_battles'], 0, 0, user_latest_stats['karma'], None, user_update_time]
                        )
                        cls._insert_daily_summary(
                            cursor, 
                            get_reset_date(current_timestamp), 
                            [1, user_latest_stats['total_battles'], user_latest_stats['pve_battles'], 0, 0, user_latest_stats['karma'], None, user_update_time]
                        )
                        conn.commit()
                        return False
                    else:
                        return True
        
                # 获取当日日期
                now_date = get_reset_date(current_timestamp)
                last_daily_summary = daily_summary[last_summary_date]
                
                # 用户当前隐藏战绩，不需要更新
                if not user_latest_stats['is_public']:
                    # 如果最新记录是公开的且更新日期不是今天，则插入一条今天的隐藏记录
                    if last_daily_summary[0] and get_reset_date(last_daily_summary[7]) != now_date:
                        cls._update_daily_summary(cursor, now_date, HIDDEN_USER_STATS, None, user_update_time)
                        conn.commit()
                    return False
                
                # 没有 pvp 或 ranked 场次变化
                if (
                    last_daily_summary[3] == user_latest_stats['pvp_battles'] and   # pvp_battles
                    last_daily_summary[4] == user_latest_stats['ranked_battles']    # ranked_battles
                ):
                    # 仅更新基本数据（total_battles, karma等），index_table 保持不变，用 last_daily_summary[6]
                    if user_update_time > last_daily_summary[7]:
                        cls._update_daily_summary(cursor, now_date, user_latest_stats, last_daily_summary[6], user_update_time)
                        conn.commit()
                    return False
                    
                # 更新条件：
                # 1. 用户没有隐藏战绩
                # 2. pvp/rank 场次存在更改（存在战斗数据）
                return True
        except Exception as e:
            if 'conn' in locals():
                conn.rollback()
            error_name = type(e).__name__
            logger.error(f'{account_id} | Database operation error')
            write_exception(
                error_type="DatabaseError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            return False