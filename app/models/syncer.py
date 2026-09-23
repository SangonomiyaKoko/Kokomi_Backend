from aiomysql.cursors import Cursor
from typing import Optional

from shard import CommonConfig, ParseUtils, UserPolicyUtils

from app.core import EnvConfig
from app.constants import ClanColor
from app.database import MySQLManager
from app.middlewares import RedisClient
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.schemas import DataIntegrityError
from app.utils import TimeUtils


class UserStatsSyncer:
    @staticmethod
    async def _init_new_user(cursor: Cursor, account_id: int, username: str | None) -> None:
        """为新用户创建基础表记录"""
        if not username:
            username = f'User_{account_id}'
        sql = """
            INSERT INTO T_user_base (
                account_id, 
                username 
            ) VALUES (
                %s, %s
            );
        """
        await cursor.execute(sql, [account_id, username])
        for table_name in CommonConfig.USER_INIT_TABLE_LIST:
            sql = f"""
                INSERT INTO {table_name} (
                    account_id
                ) VALUES (
                    %s
                );
            """
            await cursor.execute(sql, [account_id])

    @staticmethod
    async def _fetch_user_base_row(cursor: Cursor, account_id: int) -> tuple | None:
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
        await cursor.execute(sql, [account_id])
        return await cursor.fetchone()

    @staticmethod
    async def _update_user_base(cursor: Cursor, account_id: int, user_data: dict, old_username: str, old_timestamp: int) -> None:
        """更新 T_user_base 表"""
        if not user_data['username']:
            return
        
        if user_data['register_time'] is None:
            # 有名称但无注册时间 -> 隐藏战绩用户
            sql = """
                UPDATE T_user_base 
                SET 
                    username = %s, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            await cursor.execute(sql, [user_data['username'], account_id])
        else:
            # 有名称和注册时间 -> 正常用户
            sql = """
                UPDATE T_user_base 
                SET 
                    username = %s, 
                    register_time = FROM_UNIXTIME(%s), 
                    insignias = %s, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            await cursor.execute(
                sql,[user_data['username'], user_data['register_time'], user_data['insignias'], account_id]
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
            await cursor.execute(sql, [account_id, old_username])

    @staticmethod
    async def _update_user_stats(cursor: Cursor, account_id: int, user_level: int, user_data: dict, current_timestamp: int, return_refresh_time: bool, activity_level: int) -> int | None:
        """更新 T_user_stats 表"""
        if user_data['is_enabled'] == 0:
            # 账号不存在
            sql = """
                UPDATE T_user_stats 
                SET 
                    is_enabled = 0, 
                    activity_level = 0, 
                    next_refresh_at = NULL,
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            await cursor.execute(sql, [account_id])
        elif user_data['is_public'] == 0:
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
            await cursor.execute(sql, [interval_seconds, account_id])
        else:
            interval_seconds = UserPolicyUtils.user_normal_policy(
                timestamp=current_timestamp,
                user_level=user_level,
                activity_level=activity_level,
                lbt=user_data['last_battle_at']
            )

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
            await cursor.execute(
                sql,
                [activity_level, user_data['total_battles'], user_data['pve_battles'],
                user_data['pvp_battles'], user_data['ranked_battles'], user_data['rating_battles'],
                user_data['karma'], user_data['last_battle_at'], interval_seconds, account_id]
            )

        if return_refresh_time:
            sql = """
                SELECT 
                    UNIX_TIMESTAMP(updated_at) 
                FROM T_user_stats
                WHERE account_id = %s;
            """
            await cursor.execute(sql, [account_id])
            data = await cursor.fetchone()
            return data[0]

    @staticmethod
    async def _update_user_battles(cursor: Cursor, account_id: int, table_name: str, user_data: dict) -> None:
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
        await cursor.execute(sql, [
            user_data['battles'], user_data['total_exp'], user_data['win_rate'], user_data['avg_damage'], 
            user_data['avg_frags'], user_data['avg_exp'], user_data['max_exp'], user_data['max_frags'], 
            user_data['max_planes'], user_data['max_damage'], user_data['max_scouting'], user_data['max_potential'], 
            account_id
        ])

    @staticmethod
    async def _update_user_cache(cursor: Cursor, account_id: int, user_data: dict, old_pvp: int) -> None:
        """更新 T_user_cache 表"""
        if user_data['is_enabled'] and user_data['is_public']:
            if old_pvp != user_data['pvp_battles']:
                sql = """
                    UPDATE T_user_cache 
                    SET 
                        is_due = TRUE 
                    WHERE account_id = %s;
                """
                await cursor.execute(sql, [account_id])
            else:
                sql = """
                    UPDATE T_user_cache 
                    SET 
                        updated_at = NOW() 
                    WHERE account_id = %s 
                      AND is_due = FALSE;
                """
                await cursor.execute(sql, [account_id])
        else:
            sql = """
                UPDATE T_user_cache 
                SET 
                    is_due = FALSE 
                WHERE account_id = %s;
            """
            await cursor.execute(sql, [account_id])

    @classmethod
    @ExceptionLogger.handle_database_exception_async
    async def refresh(cls, account_id: int, api_result: dict, return_refresh_time: bool = False) -> int | None:
        """基于用户基本信息接口的数据，刷新数据库的 user_stats 表
        
        eg. https://vortex.worldofwarships.asia/api/accounts/2023619512/
        
        Returns:
            None: 成功
            str: 错误类型名称
        """
        current_timestamp = TimeUtils.timestamp()
        user_data = ParseUtils.user_basic_data(
            region=EnvConfig.REGION,
            account_id=account_id,
            response=api_result
        )
        activity_level = UserPolicyUtils.user_activity_level(
            timestamp=current_timestamp,
            lbt=user_data['last_battle_at']
        )

        async with MySQLManager.auto_transaction_cursor() as cursor:
            # 从数据库中读取用户的username
            existing = await cls._fetch_user_base_row(cursor, account_id)
            
            if existing is None:
                lock_key = 'refresh_lock:user_insert'
                error, lock = JSONResponse.extract_data(
                    response=await RedisClient.acquire_lock(lock_key)
                )
                if error:
                    return lock
                if not lock:
                    return JSONResponse.API_AcqurieLockFailed
                await cls._init_new_user(cursor, account_id, user_data['username'])
                await RedisClient.drop(lock_key)
                old_username = user_data['username']
                old_timestamp = None
                random = 0
                ranked = 0
                user_level = None
            else:
                old_username, old_timestamp, random, ranked, user_level = existing

            if random is None or ranked is None:
                raise DataIntegrityError(account_id)

            # 更新 T_user_base
            await cls._update_user_base(cursor, account_id, user_data, old_username, old_timestamp)
            
            # 更新 T_user_stats
            update_timestamp = await cls._update_user_stats(cursor, account_id, user_level, user_data, current_timestamp, return_refresh_time, activity_level)

            # 更新 T_user_random / T_user_ranked
            await cls._update_user_battles(cursor, account_id, 'T_user_random', user_data['random_stats'])
            await cls._update_user_battles(cursor, account_id, 'T_user_ranked', user_data['ranked_stats'])
            
            # 更新 T_user_cache
            await cls._update_user_cache(cursor, account_id, user_data, random)
            
        return JSONResponse.success(update_timestamp)
    
class UserClanSyncer:
    @staticmethod
    async def _is_existing(cursor: Cursor, clan_id: int) -> tuple | None:
        sql = """
            SELECT 
                1 
            FROM T_clan_base 
            WHERE clan_id = %s;
        """
        await cursor.execute(sql, [clan_id])
        return await cursor.fetchone()
    
    @staticmethod
    async def _init_new_clan(cursor: Cursor, clan_id: int, clan_tag: str, league: int) -> None:
        """为新用户创建基础表记录"""
        if not clan_tag:
            clan_tag = f'N/A'
        sql = """
            INSERT INTO T_clan_base (
                clan_id, 
                tag, 
                league,
                updated_at
            ) VALUES (
                %s, %s, %s, NOW()
            );
        """
        await cursor.execute(sql, [clan_id, clan_tag, league])
        for table_name in CommonConfig.CLAN_INIT_TABLE_LIST:
            sql = f"""
                INSERT INTO {table_name} (
                    clan_id
                ) VALUES (
                    %s
                );
            """
            await cursor.execute(sql, [clan_id])

    @staticmethod
    async def _update_user_base(cursor: Cursor, clan_id: int, clan_tag: str, league: int) -> None:
        """批量更新公会成员关系

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
        """
        sql = """
            UPDATE T_clan_base
            SET 
                tag = %s, 
                league = %s, 
                updated_at = NOW() 
            WHERE clan_id = %s;
        """
        await cursor.execute(sql, [clan_tag, league, clan_id])

    @staticmethod
    async def _update_user_clan(cursor: Cursor, account_id: int, clan_id: Optional[int]) -> None:
        """批量更新公会成员关系

        Args:
            cursor: 数据库游标
            clan_id: 公会 ID
            user_ids: 当前公会成员 ID 列表
        """
        sql = f"""
            UPDATE T_user_clan 
            SET 
                clan_id = %s, 
                updated_at = NOW() 
            WHERE account_id = %s;
        """
        await cursor.execute(sql, [clan_id, account_id])

    @classmethod
    @ExceptionLogger.handle_database_exception_async
    async def refresh(cls, account_id: int, result: dict) -> str | None:
        """基于公会成员接口数据刷新数据库中的公会成员信息

        Args:
            conn: 数据库连接
            clan_id: 公会 ID
            result: API 返回的公会成员数据

        Returns:
            None: 成功
            str: 失败时返回错误类型名称
        """

        async with MySQLManager.auto_transaction_cursor() as cursor:
            clan_id = result.get('clan_id')
            if clan_id:
                clan_tag = result.get('clan', {}).get('tag')
                league = ClanColor.CLAN_COLOR_INDEX.get(
                    result.get('clan', {}).get('color'), 5
                )
                existing = await cls._is_existing(cursor, clan_id)
                if not existing:
                    await cls._init_new_clan(cursor, clan_id, clan_tag, league)
                else:
                    await cls._update_user_base(cursor, clan_id, clan_tag, league)
            await cls._update_user_clan(cursor, account_id, clan_id)

        return JSONResponse.API_1000_Success