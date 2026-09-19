from contextlib import contextmanager
from typing import Any, Iterator

from pymysql import Connection
from pymysql.cursors import Cursor

from .logger import logger


@contextmanager
def mysql_read_only(
    conn: Connection, desc: Any = None
) -> Iterator[Cursor]:
    """MySQL 上下文管理器，仅读取"""
    
    try:
        with conn.cursor() as cur:
            yield cur
    except Exception as e:
        error_name = type(e).__name__
        logger.error(
            '%sDatabase read error: %s'
            , f'{desc} | ' if desc else ''
            , error_name
        )
        raise

@contextmanager
def mysql_transaction(
    conn: Connection, desc: Any = None
) -> Iterator[Cursor]:
    """MySQL 事务上下文管理器"""
    try:
        with conn.cursor() as cur:
            yield cur
    except Exception as e:
        conn.rollback()
        error_name = type(e).__name__
        logger.error(
            '%sDatabase operation error: %s'
            , f'{desc} | ' if desc else ''
            , error_name
        )
        raise
    else:
        conn.commit()


class BasicDataRepository:

    @staticmethod
    def load_max_id(cursor: Cursor) -> int:
        """读取 T_user_stats 表中自增 ID 最大值确定数据读取的终点"""
        sql = "SELECT MAX(id) FROM T_user_stats;"
        cursor.execute(sql)

        data = cursor.fetchone()
        if data[0] is None:
            return 0
        
        return data[0]

    @staticmethod
    def load_table_batch(
        cursor: Cursor, start_id: int, end_id: int
    ) -> tuple:
        """从 T_user_stats 表中读取一个批次的数据"""
        sql = """
            SELECT 
                account_id, 
                is_enabled, 
                activity_level, 
                UNIX_TIMESTAMP(next_refresh_at), 
                UNIX_TIMESTAMP(updated_at) 
            FROM T_user_stats
            WHERE id BETWEEN %s AND %s;
        """
        cursor.execute(sql, [start_id, end_id])
        rows = cursor.fetchall()

        return rows

    @staticmethod
    def write_stats(
        cursor: Cursor, stats_data: dict
    ) -> None:
        """ 将 RefreshPlanStats 的统计数据写入数据库"""
        # 更新统计总数：planned_users
        sql = """
            UPDATE T_table_meta 
            SET 
                metric_value = %s 
            WHERE metric_key = %s;
        """
        cursor.execute(sql, [stats_data['planned_count'], 'planned_users'])

        # 更新各刷新状态的人数
        sql = """
            UPDATE T_refresh_stats 
            SET 
                user_count = %s, 
                updated_at = NOW() 
            WHERE status = %s;
        """
        cursor.executemany(sql, stats_data['refresh_stats'])

        # 更新用户 activity_distribution
        sql = """
            UPDATE T_user_activity 
            SET 
                user_count = %s, 
                updated_at = NOW() 
            WHERE user_level = %s;
        """
        cursor.executemany(sql, stats_data['distribution'])

        # 更新每小时的计划人数（planned_hour 1~24）
        sql = """
            UPDATE T_refresh_hourly_stats 
            SET 
                planned_users = %s, 
                updated_at = NOW() 
            WHERE planned_hour = %s;
        """
        cursor.executemany(sql, stats_data['hourly_counts'])

        # 应用重均衡产生的用户迁移（调整 next_refresh_at）
        if stats_data['all_migrations']:
            sql = """
                UPDATE T_user_stats 
                SET 
                    next_refresh_at = next_refresh_at - INTERVAL %s HOUR 
                WHERE account_id = %s;
            """
            cursor.executemany(sql, stats_data['all_migrations'])