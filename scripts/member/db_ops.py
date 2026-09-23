from pymysql.cursors import Cursor
from shard import CommonConfig


class BasicDataRepository:

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
    ) -> list:
        """获取本地储存的工会内用户 ID 列表"""
        sql = """
            SELECT account_id 
            FROM T_user_clan 
            WHERE clan_id = %s;
        """
        cursor.execute(sql, [clan_id])
        return [row[0] for row in cursor.fetchall()]

    @staticmethod
    def get_existing_ids(
        cursor: Cursor,
        user_ids: list[int]
    ) -> list:
        """读取存在于数据库的用户 ID 列表"""
        if not user_ids:
            return []

        placeholders = ",".join(["%s"] * len(user_ids))
        sql = f"""
            SELECT account_id
            FROM T_user_base
            WHERE account_id IN ({placeholders});
        """
        cursor.execute(sql, user_ids)
        return [
            row[0] for row in cursor.fetchall()
        ]

    @staticmethod
    def get_existing_users(
        cursor: Cursor,
        user_ids: list[int]
    ) -> dict:
        """读取存在于数据库用户的 clan 信息

        Returns:
            {account_id: (clan_id, is_null), ...}
            is_null 标记该用户公会信息是否未曾更新
        """
        if not user_ids:
            return {}

        placeholders = ",".join(["%s"] * len(user_ids))
        sql = f"""
            SELECT
                account_id,
                clan_id,
                updated_at IS NULL
            FROM T_user_clan
            WHERE account_id IN ({placeholders});
        """
        cursor.execute(sql, user_ids)
        return {
            row[0]: (row[1], row[2])
            for row in cursor.fetchall()
        }

    @staticmethod
    def init_new_users(cursor: Cursor, missing_users: dict[int, str]) -> None:
        """为新用户创建基础表记录"""
        account_ids = list(missing_users.keys())
        if not account_ids:
            return

        # 1. 批量插入 T_user_base
        values_list = []
        params = []
        for account_id in account_ids:
            values_list.append("(%s, %s)")
            params.extend([account_id, missing_users[account_id]])
        
        sql = f"""
            INSERT INTO T_user_base (
                account_id, username
            ) VALUES 
                {','.join(values_list)}
            ;
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
                INSERT INTO {table_name} (
                    account_id
                ) VALUES 
                    {','.join(values_list)};
            """
            cursor.execute(sql, params)

    @staticmethod
    def write_stats(
        cursor: Cursor, stats_data: dict
    ) -> None:
        """ 将 RefreshPlanStats 的统计数据写入数据库"""
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
        cursor.executemany(sql, stats_data['distribution'])

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
                WHERE clan_id = %s;
            """
            cursor.executemany(sql, stats_data['all_migrations'])