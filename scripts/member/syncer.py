import json
import traceback

from pymysql import Connection
from pymysql.cursors import Cursor

from shard import PolicyUtils

from .db_ops import mysql_transaction
from .logger import logger, write_exception


class ClanUsersSyncer:
    """工会基础信息同步器"""
    @staticmethod
    def _disable_empty_clan(
        cursor: Cursor, 
        clan_id: int
    ) -> None:
        """将无成员的公会标记为不可用并清理成员关系"""
        sql = """
            UPDATE T_clan_users 
            SET 
                is_enabled = 0, 
                activity_level = 0, 
                member_count = 0, 
                member_ids = NULL, 
                next_refresh_at = NULL,
                updated_at = CURRENT_TIMESTAMP 
            WHERE clan_id = %s;
        """
        cursor.execute(sql, [clan_id])

        sql = """
            SELECT 
                account_id 
            FROM T_user_clan 
            WHERE clan_id = %s;
        """
        cursor.execute(sql, [clan_id])
        for row in cursor.fetchall():
            sql = """
                UPDATE T_user_clan 
                SET 
                    clan_id = NULL, 
                    updated_at = CURRENT_TIMESTAMP 
                WHERE account_id = %s;
            """
            cursor.execute(sql, [row[0]])

            sql = """
                INSERT INTO T_clan_action (
                    clan_id, 
                    account_id, 
                    action_type
                ) VALUES (
                    %s, %s, %s
                );
            """
            cursor.execute(sql, [clan_id, row[0], 2])
    
    @staticmethod
    def _remove_left_members(cursor: Cursor, clan_id: int, current_ids: set) -> None:
        """清理已退出公会的成员关系

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
            current_ids: 当前公会成员 ID 集合
        """
        sql = """
            SELECT 
                account_id 
            FROM T_user_clan 
            WHERE clan_id = %s;
        """
        cursor.execute(sql, [clan_id])
        for row in cursor.fetchall():
            if row[0] not in current_ids:
                sql = """
                    UPDATE T_user_clan 
                    SET 
                        clan_id = NULL, 
                        updated_at = NOW() 
                    WHERE account_id = %s;
                """
                cursor.execute(sql, [row[0]])

    @staticmethod
    def _update_member_relations(cursor: Cursor, clan_id: int, user_ids: list) -> None:
        """批量更新公会成员关系

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
            user_ids: 当前公会成员 ID 列表
        """
        placeholders = ",".join(["%s"] * len(user_ids))
        sql = f"""
            UPDATE T_user_clan 
            SET 
                clan_id = %s, 
                updated_at = NOW() 
            WHERE account_id IN ({placeholders});
        """
        cursor.execute(sql, [clan_id] + user_ids)

    @staticmethod
    def _update_clan_users(cursor: Cursor, clan_id: int,  user_ids: list) -> None:
        """更新公会成员统计信息

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
            user_ids: 当前公会成员 ID 列表
        """
        sql = """
            UPDATE T_clan_users 
            SET 
                is_enabled = 1, 
                activity_level = %s,
                member_count = %s, 
                member_ids = %s, 
                next_refresh_at = DATE_ADD(NOW(), INTERVAL %s SECOND), 
                updated_at = NOW()
            WHERE clan_id = %s;
        """
        activity_level = PolicyUtils.clan_activity_level(len(user_ids))
        interval_seconds = PolicyUtils.clan_refresh_interval(activity_level)
        cursor.execute(sql, [activity_level, len(user_ids), json.dumps(user_ids), interval_seconds, clan_id])

    @staticmethod
    def _record_member_changes(cursor: Cursor, clan_id: int, old_data: dict, user_ids: list) -> None:
        """记录公会成员的加入和退出行为

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
            old_data: 旧成员数据 (member_ids_json, updated_at)
            user_ids: 当前公会成员 ID 列表
        """
        if not old_data or not old_data[1]:
            return

        old_ids = json.loads(old_data[0] if old_data[0] else '[]')
        added_ids = [uid for uid in user_ids if uid not in old_ids]
        removed_ids = [uid for uid in old_ids if uid not in user_ids]

        for added_id in added_ids:
            sql = """
                INSERT INTO T_clan_action (
                    clan_id, 
                    account_id, 
                    action_type
                ) VALUES (
                    %s, %s, %s
                );
            """
            cursor.execute(sql, [clan_id, added_id, 1])

        for removed_id in removed_ids:
            sql = """
                INSERT INTO T_clan_action (
                    clan_id, 
                    account_id, 
                    action_type
                ) VALUES (
                    %s, %s, %s
                );
            """
            cursor.execute(sql, [clan_id, removed_id, 2])

    @classmethod
    def refresh(
        cls, 
        conn: Connection, 
        clan_id: int, 
        users: dict,
        old_data: tuple
    ) -> int:
        """基于公会成员接口数据刷新数据库中的公会成员信息"""
        user_ids = list(users.keys())

        try:
            with mysql_transaction(conn, clan_id) as cursor:
                if len(user_ids) == 0:
                    cls._disable_empty_clan(cursor, clan_id)
                else:
                    cls._remove_left_members(cursor, clan_id, set(user_ids))
                    cls._update_member_relations(cursor, clan_id, user_ids)
                    cls._update_clan_users(cursor, clan_id, user_ids)
                    cls._record_member_changes(cursor, clan_id, old_data, user_ids)
        except Exception as e:
            error_name = type(e).__name__
            error_id = write_exception(
                error_type="DatabaseError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            logger.error(f'{clan_id} | ERROR - {error_name} - {error_id}')