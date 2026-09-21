from typing import Union, Optional

from pymysql.cursors import Cursor
from dbutils.pooled_db import PooledDB

from shard import (
    MySQLOPS,
    UserPolicyUtils, 
    UserBasicDataDict
)


class UserStatsSyncer:
    """用户基础信息同步器"""

    @staticmethod
    def _fetch_user_base_row(
        cursor: Cursor,
        account_id: int
    ) -> Optional[tuple]:
        """从 T_user_base 表查询用户基本信息行"""
        sql = """
            SELECT
                b.username,
                UNIX_TIMESTAMP(b.updated_at),
                s.pvp_battles,
                s.ranked_battles,
                IFNULL(c.user_level, 0)
            FROM T_user_base b
            LEFT JOIN T_user_stats s
              ON b.account_id = s.account_id
            LEFT JOIN T_user_config c
              ON b.account_id = c.account_id
            WHERE b.account_id = %s;
        """
        cursor.execute(sql, [account_id])
        return cursor.fetchone()

    @staticmethod
    def _update_user_base(
        cursor: Cursor,
        account_id: int,
        user_data: dict,
        old_username: str,
        old_timestamp: int
    ) -> None:
        """更新 T_user_base 表"""
        if not user_data['is_enabled']:
            return
        elif not user_data['is_public']:
            sql = """
                UPDATE T_user_base
                SET
                    username = %s,
                    updated_at = NOW()
                WHERE account_id = %s;
            """
            cursor.execute(sql, [user_data['username'], account_id])
        else:
            sql = """
                UPDATE T_user_base
                SET
                    username = %s,
                    register_time = FROM_UNIXTIME(%s),
                    insignias = %s,
                    updated_at = NOW()
                WHERE account_id = %s;
            """
            cursor.execute(
                sql, [
                    user_data['username'],
                    user_data['register_time'],
                    user_data['insignias'],
                    account_id
                ]
            )

        # 检测昵称变更
        if old_timestamp and old_username != user_data['username']:
            sql = """
                INSERT INTO T_user_action (
                    account_id,
                    username
                ) VALUES (
                    %s, %s
                );
            """
            cursor.execute(sql, [account_id, old_username])

    @staticmethod
    def _update_user_stats(
        cursor: Cursor,
        account_id: int,
        user_level: int,
        activity_level: int,
        user_data: dict,
        current_timestamp: int
    ) -> int:
        """更新 T_user_stats 表"""
        if not user_data['is_enabled']:
            # 账号不存在
            sql = """
                UPDATE T_user_stats
                SET
                    is_enabled = 0,
                    is_public = 0,
                    activity_level = 0,
                    next_refresh_at = NULL,
                    updated_at = NOW()
                WHERE account_id = %s;
            """
            cursor.execute(sql, [account_id])
        elif not user_data['is_public']:
            # 账号隐藏战绩
            sql = """
                UPDATE T_user_stats
                SET
                    is_enabled = 1,
                    is_public = 0,
                    activity_level = 0,
                    next_refresh_at = DATE_ADD(NOW(), INTERVAL %s SECOND),
                    updated_at = NOW()
                WHERE account_id = %s;
            """
            interval_seconds = UserPolicyUtils.user_hidden_policy(user_level)
            cursor.execute(sql, [interval_seconds, account_id])
        else:
            sql = """
                UPDATE T_user_stats
                SET
                    is_enabled = 1,
                    is_public = 1,
                    activity_level = %s,
                    total_battles = %s,
                    pve_battles = %s,
                    pvp_battles = %s,
                    ranked_battles = %s,
                    rating_battles = %s,
                    karma = %s,
                    last_battle_at = FROM_UNIXTIME(%s),
                    next_refresh_at = DATE_ADD(NOW(), INTERVAL %s SECOND),
                    updated_at = NOW()
                WHERE account_id = %s;
            """

            interval_seconds = UserPolicyUtils.user_normal_policy(
                timestamp=current_timestamp,
                user_level=user_level,
                activity_level=activity_level,
                lbt=user_data['last_battle_at']
            )
            cursor.execute(
                sql,
                [
                    activity_level,
                    user_data['total_battles'],
                    user_data['pve_battles'],
                    user_data['pvp_battles'],
                    user_data['ranked_battles'],
                    user_data['rating_battles'],
                    user_data['karma'],
                    user_data['last_battle_at'],
                    interval_seconds,
                    account_id
                ]
            )

        sql = """
            SELECT
                UNIX_TIMESTAMP(updated_at)
            FROM T_user_stats
            WHERE account_id = %s;
        """
        cursor.execute(sql, [account_id])
        return cursor.fetchone()[0]

    @staticmethod
    def _update_user_battles(
        cursor: Cursor,
        account_id: int,
        table_name: str,
        user_data: dict
    ) -> None:
        """更新 T_user_random / T_user_ranked 表"""
        if user_data is None:
            return

        sql = f"""
            UPDATE {table_name}
            SET
                battles = %s,
                total_exp = %s,
                win_rate = %s,
                avg_damage = %s,
                avg_frags = %s,
                avg_exp = %s,
                max_exp = %s,
                max_frags = %s,
                max_planes = %s,
                max_damage = %s,
                max_scouting = %s,
                max_potential = %s,
                updated_at = NOW()
            WHERE account_id = %s;
        """
        cursor.execute(sql, [
            user_data['battles'],
            user_data['total_exp'],
            user_data['win_rate'],
            user_data['avg_damage'],
            user_data['avg_frags'],
            user_data['avg_exp'],
            user_data['max_exp'],
            user_data['max_frags'],
            user_data['max_planes'],
            user_data['max_damage'],
            user_data['max_scouting'],
            user_data['max_potential'],
            account_id
        ])

    @staticmethod
    def _update_user_cache(
        cursor: Cursor,
        account_id: int,
        user_data: dict,
        old_pvp: int
    ) -> None:
        """更新 T_user_cache 表"""
        if user_data['is_enabled'] and user_data['is_public']:
            if old_pvp != user_data['pvp_battles']:
                sql = """
                    UPDATE T_user_cache
                    SET
                        is_due = TRUE
                    WHERE account_id = %s;
                """
                cursor.execute(sql, [account_id])
            else:
                sql = """
                    UPDATE T_user_cache
                    SET
                        updated_at = NOW()
                    WHERE account_id = %s
                      AND is_due = FALSE;
                """
                cursor.execute(sql, [account_id])
        else:
            sql = """
                UPDATE T_user_cache
                SET
                    is_due = FALSE
                WHERE account_id = %s;
            """
            cursor.execute(sql, [account_id])

    @classmethod
    def refresh(
        cls,
        db_pool: PooledDB,
        timestamp: int,
        account_id: int,
        user_data: UserBasicDataDict,
        activity_level: int
    ) -> Union[int, str]:
        """基于用户基本信息接口的数据，刷新数据库的用户数据表
        
        正常返回整数类型的更新时间戳，错误返回错误标识字符串
        """
        try:
            with db_pool.connection() as conn, MySQLOPS.transaction(conn) as cursor:
                # 从数据库中读取用户的基本信息
                existing = cls._fetch_user_base_row(
                    cursor=cursor, 
                    account_id=account_id
                )
                if existing is None:
                    return "UserNotInDB"

                # 此处读取 ranked 并无实际需求，仅为后续拓展预留
                old_name, old_ts, random, ranked, user_level = existing
                if random is None or ranked is None:
                    return "DataIntegrityError"

                # 更新 T_user_base
                cls._update_user_base(
                    cursor=cursor, 
                    account_id=account_id, 
                    user_data=user_data, 
                    old_username=old_name, 
                    old_timestamp=old_ts
                )
                
                # 更新 T_user_stats
                update_timestamp = cls._update_user_stats(
                    cursor=cursor, 
                    account_id=account_id, 
                    user_level=user_level, 
                    activity_level=activity_level, 
                    user_data=user_data, 
                    current_timestamp=timestamp
                )

                # 更新 T_user_random / T_user_ranked
                cls._update_user_battles(
                    cursor=cursor, 
                    account_id=account_id, 
                    table_name='T_user_random', 
                    user_data=user_data['random_stats']
                )
                cls._update_user_battles(
                    cursor=cursor, 
                    account_id=account_id, 
                    table_name='T_user_ranked', 
                    user_data=user_data['ranked_stats']
                )

                # 更新 T_user_cache
                cls._update_user_cache(
                    cursor=cursor, 
                    account_id=account_id, 
                    user_data=user_data, 
                    old_pvp=random
                )

                return update_timestamp
        except Exception as e:
            # 通过返回错误标识符用于记录错误指标
            # Celery 任务中不捕获该异常以避免日志风暴
            return type(e).__name__

    