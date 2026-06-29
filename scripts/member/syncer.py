import json
import time
from redis import Redis
from pymysql.cursors import Cursor

from logger import logger
from settings import (
    USER_INIT_TABLE_LIST,
    CLAN_ACTIVITY_STRATEGY,
    CLAN_ACTIVITY_THRESHOLDS
)


def acquire_lock(
    redis_client: Redis,
    lock_key: str,
    expire_seconds: int = 5,
    max_retries: int = 5,
    retry_interval: float = 0.2
) -> bool:
    """获取 Redis 分布式锁

    Args:
        redis_client: Redis 客户端
        lock_key: 锁的键名
        expire_seconds: 锁的过期时间，防止死锁
        max_retries: 最大重试次数
        retry_interval: 重试间隔
    """
    try:
        for _ in range(1, max_retries + 1):
            acquired = redis_client.set(
                lock_key, 1, nx=True, ex=expire_seconds
            )

            if acquired:
                return True

            time.sleep(retry_interval)
    except Exception:
        logger.warning('Failed to set the distributed lock')

    return False

def release_lock(
    redis_client: Redis,
    lock_key: str
) -> None:
    """释放 Redis 分布式锁

    Args:
        redis_client: Redis 客户端
        lock_key: 锁的键名
    """
    try:
        redis_client.delete(lock_key)
    except Exception:
        logger.warning('Failed to release the distributed lock')

class ClanUsersSyncer:
    @staticmethod
    def _get_activity_level(members: int | None) -> int:
        """根据工会返回活跃等级（0-3）"""
        for threshold, level in CLAN_ACTIVITY_THRESHOLDS:
            if members <= threshold:
                return level

        return 0
    
    @staticmethod
    def _get_existing_members(cursor: Cursor, clan_id: int) -> tuple:
        """获取公会当前的成员列表和更新时间

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
        """
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
    def _get_existing_users(cursor: Cursor, user_ids: list[int]) -> set:
        """获取公会当前的成员列表和更新时间

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
        """
        placeholders = ",".join(["%s"] * len(user_ids))
        sql = f"""
            SELECT account_id 
            FROM T_user_base 
            WHERE account_id IN ({placeholders});
        """
        cursor.execute(sql, user_ids)
        return {row[0] for row in cursor.fetchall()}

    @staticmethod
    def _disable_empty_clan(cursor: Cursor, clan_id: int) -> None:
        """将无成员的公会标记为不可用并清理成员关系

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
        """
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
    def _init_new_users(cursor: Cursor, account_ids: list, users: dict) -> None:
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
        for table_name in USER_INIT_TABLE_LIST:
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
    def _update_clan_users(cursor: Cursor, clan_id: int, activity_level: int, user_ids: list) -> None:
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
        interval_seconds = CLAN_ACTIVITY_STRATEGY.get(f"0-{activity_level}", 30*86400)
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
    def refresh(cls, redis_client: Redis, cursor: Cursor, clan_id: int, users: dict) -> int:
        """基于公会成员接口数据刷新数据库中的公会成员信息

        Args:
            conn: 数据库连接
            clan_id: 公会 ID
            result: API 返回的公会成员数据
        """
        # 提取公会成员映射
        user_ids = list(users.keys())

        if len(user_ids) == 0:
            cls._disable_empty_clan(cursor, clan_id)
            return 0
        
        activity_level = cls._get_activity_level(len(user_ids))
            
        old_data = cls._get_existing_members(cursor, clan_id)
        existing_ids = cls._get_existing_users(cursor, user_ids)
        missing_ids = [uid for uid in user_ids if uid not in existing_ids]

        if missing_ids:
            # 尽量避免并发写可能存在的问题，先获取锁再写
            lock_key = 'refresh_lock:user_insert'
            lock = acquire_lock(redis_client, lock_key)
            if not lock:
                logger.warning('Acquire distributed lock failed')
                return 0
            cls._init_new_users(cursor, missing_ids, users)
            # 写入完成释放lock
            release_lock(redis_client, lock_key)

        cls._remove_left_members(cursor, clan_id, set(user_ids))
        cls._update_member_relations(cursor, clan_id, user_ids)
        cls._update_clan_users(cursor, clan_id, activity_level, user_ids)
        cls._record_member_changes(cursor, clan_id, old_data, user_ids)

        return len(missing_ids)