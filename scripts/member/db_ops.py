from contextlib import contextmanager
from typing import Any, Iterator

from pymysql import Connection
from pymysql.cursors import Cursor
from shard import CommonConfig

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


class MySQLRepository:

    @staticmethod
    def load_max_id(cursor: Cursor) -> int:
        """读取 T_clan_users 表中自增 ID 最大值确定数据读取的终点"""
        sql = "SELECT MAX(id) FROM T_clan_users;"
        cursor.execute(sql)

        data = cursor.fetchone()
        if data[0] is None:
            return 0

        return data[0]

    @staticmethod
    def load_table_batch(
        cursor: Cursor, start_id: int, end_id: int
    ) -> tuple:
        """从 T_clan_users 表中读取一个批次的数据"""
        sql = """
            SELECT
                clan_id,
                is_enabled,
                activity_level,
                UNIX_TIMESTAMP(next_refresh_at),
                UNIX_TIMESTAMP(updated_at)
            FROM T_clan_users
            WHERE id BETWEEN %s AND %s;
        """
        cursor.execute(sql, [start_id, end_id])
        rows = cursor.fetchall()

        return rows

    @staticmethod
    def get_existing_members(
        cursor: Cursor, 
        clan_id: int
    ) -> tuple:
        """获取公会当前的成员列表和更新时间"""
        sql = """
            SELECT 
                member_ids, 
                UNIX_TIMESTAMP(updated_at) 
            FROM T_clan_users 
            WHERE clan_id = %s;
        """
        cursor.execute(sql, [clan_id])
        return cursor.fetchone()

    @staticmethod
    def get_existing_users(
        cursor: Cursor, 
        user_ids: list[int]
    ) -> set:
        """获取公会当前的成员列表和更新时间"""
        placeholders = ",".join(["%s"] * len(user_ids))
        sql = f"""
            SELECT account_id 
            FROM T_user_base 
            WHERE account_id IN ({placeholders});
        """
        cursor.execute(sql, user_ids)
        return {row[0] for row in cursor.fetchall()}

    @staticmethod
    def init_new_users(cursor: Cursor, account_ids: list, users: dict) -> None:
        """为新用户创建基础表记录"""
        
        if not account_ids:
            return

        # 1. 批量插入 T_user_base
        values_list = []
        params = []
        for account_id in account_ids:
            values_list.append("(%s, %s)")
            params.extend([account_id, users[account_id]])
        
        sql = f"""
            INSERT INTO T_user_base (account_id, username) 
            VALUES {','.join(values_list)};
        """
        cursor.execute(sql, params)

        # 2. 批量插入所有子表
        for table_name in CommonConfig.USER_INIT_TABLE_LIST:
            values_list = []
            params = []
            for account_id in account_ids:
                values_list.append("(%s)")
                params.append(account_id)
            
            sql = f"""
                INSERT INTO {table_name} (account_id) 
                VALUES {','.join(values_list)};
            """
            cursor.execute(sql, params)

    @staticmethod
    def write_stats(
        cursor: Cursor, stats_data: dict
    ) -> None:
        """ 将 RefreshPlanStats 的统计数据写入数据库"""
        # 更新统计总数：planned_clans
        sql = """
            UPDATE T_table_meta 
            SET 
                metric_value = %s 
            WHERE metric_key = %s;
        """
        cursor.execute(sql, [stats_data['planned_count'], 'planned_clans'])

        # 更新各刷新状态的公会数
        sql = """
            UPDATE T_refresh_stats 
            SET 
                clan_count = %s, 
                updated_at = NOW() 
            WHERE status = %s;
        """
        cursor.executemany(sql, stats_data['refresh_stats'])

        # 更新公会 activity_distribution
        sql = """
            UPDATE T_clan_activity 
            SET 
                clan_count = %s, 
                updated_at = NOW() 
            WHERE clan_level = %s;
        """
        cursor.executemany(sql, stats_data['activity_distribution'])

        # 更新每小时的计划公会数（planned_hour 1~24）
        sql = """
            UPDATE T_refresh_hourly_stats 
            SET 
                planned_clans = %s, 
                updated_at = NOW() 
            WHERE planned_hour = %s;
        """
        cursor.executemany(sql, stats_data['hourly_counts'])

        # 应用重均衡产生的公会迁移（调整 next_refresh_at）
        if stats_data['all_migrations']:
            sql = """
                UPDATE T_clan_users 
                SET 
                    next_refresh_at = next_refresh_at - INTERVAL %s HOUR 
                WHERE account_id = %s;
            """
            cursor.executemany(sql, stats_data['all_migrations'])