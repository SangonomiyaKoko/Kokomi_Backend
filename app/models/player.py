import json

from app.core import EnvConfig
from app.database import MySQLManager
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.schemas import DataIntegrityError
from app.utils import TimeUtils, StringUtils


class DemoPlayerModel:
    @ExceptionLogger.handle_database_exception_async
    async def read_base(account_id: int):
        '''
        从数据库中获取用户的基本数据
        '''
        async with MySQLManager.read_only_cursor() as cur:
            data = {
                'region': EnvConfig.REGION,
                'user_id': account_id,
                'username': None,
                'is_enabled': False,
                'is_public': False
            }
            # 读user_base库
            sql = """
                SELECT
                    username
                FROM T_user_base
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            row = await cur.fetchone()
            if not row:
                return JSONResponse.API_1000_Success
            data['username'] = row[0]
            # 读user_stats库
            sql = """
                SELECT
                    is_enabled,
                    is_public,
                    activity_level,
                    total_battles, 
                    UNIX_TIMESTAMP(next_refresh_at)
                FROM T_user_stats
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            row = await cur.fetchone()
            if row:
                data['is_enabled'] = row[0]
                data['is_public'] = row[1]
            if not data['is_enabled'] or not data['is_public']:
                return JSONResponse.success(data)
            data['activity_level'] = row[2]
            data['total_battles'] = row[3]
            data['next_refresh_at'] = TimeUtils.fromtimestamp(row[4])
            # 读user_config库
            sql = """
                SELECT
                    user_level,
                    storage_limit,
                    query_count,
                    UNIX_TIMESTAMP(last_query_at)
                FROM T_user_config
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            row = await cur.fetchone()
            if row:
                data['user_level'] = row[0]
                data['storage_limit'] = row[1]
                data['query_count'] = row[2]
                data['last_query_time'] = TimeUtils.fromtimestamp(row[3])
            # 读user_clan库
            sql = """
                SELECT
                    clan_id
                FROM T_user_clan
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            row = await cur.fetchone()
            if row:
                data['clan_id'] = row[0]
            data['now_iso_time'] = TimeUtils.now_iso()[:19].replace('T', ' ')
            return JSONResponse.success(data)
        
    @ExceptionLogger.handle_database_exception_async
    async def set_user_status(account_id: int, status: int):
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                UPDATE T_user_stats 
                SET is_enabled = %s 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [status, account_id])
            if status == 0:
                sql = """
                    UPDATE T_user_cache 
                    SET is_due = FALSE 
                    WHERE account_id = %s;
                """
                await cur.execute(sql, [account_id])
            return JSONResponse.API_1000_Success

    @ExceptionLogger.handle_database_exception_async
    async def remove_user_ranking(account_id: int, ship_ids: list[int]):
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                DELETE FROM T_ship_pvp_leaderboard 
                WHERE ship_id = %s AND account_id = %s;
            """
            params = [(ship_id, account_id) for ship_id in ship_ids]
            await cur.executemany(sql, params)
            return JSONResponse.API_1000_Success

class PlayerModel:
    @ExceptionLogger.handle_database_exception_async
    async def record_query(account_id: int):
        """记录一次用户查询"""
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                UPDATE T_user_config
                SET
                    query_count = query_count + 1,
                    last_query_at = NOW()
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            return JSONResponse.API_1000_Success
        
    @ExceptionLogger.handle_database_exception_async
    async def set_user_due(account_id: int):
        """设置用户缓存数据状态为待更新"""
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                UPDATE T_user_cache
                SET
                    is_due = TRUE 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            return JSONResponse.API_1000_Success
        
    @ExceptionLogger.handle_database_exception_async
    async def get_user_name_and_clan(account_id: int):
        async with MySQLManager.read_only_cursor() as cur:
            result = {}
            sql = """
                SELECT 
                    account_id,
                    username,
                    UNIX_TIMESTAMP(register_time),
                    insignias,
                    clan_id,
                    clan_tag,
                    league
                FROM V_user_basic_with_clan
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            data = await cur.fetchone()
            if not data:
                return JSONResponse.API_1000_Success
            if data[4] is None:
                clan_data = None
            else:
                clan_data = {
                    'clan_id': data[4],
                    'tag': data[5],
                    'league': data[6]
                }
            result['basic'] = {
                'region': EnvConfig.REGION,
                'user_id': data[0],
                'username': data[1],
                'created_at': data[2],
                'clan': clan_data,
                'insignias': StringUtils.parse_insignias(data[3])
            }
            
            # 读取用户的缓存信息，检查是否处于隐藏战绩状态
            sql = """
                SELECT 
                    is_enabled, 
                    is_public, 
                    UNIX_TIMESTAMP(updated_at) 
                FROM T_user_stats 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            data = await cur.fetchone()
            if not data:
                raise DataIntegrityError(account_id)
            
            if data[2] is None:
                result['stats'] = False
            elif not data[0]:
                result['stats'] = None
            elif not data[1]:
                result['stats'] = False
            else:
                result['stats'] = True
            return JSONResponse.success(result)
        
    @ExceptionLogger.handle_database_exception_async
    async def get_user_cache(account_id: int):
        async with MySQLManager.read_only_cursor() as cur:
            result = {}
            sql = """
                SELECT 
                    cache 
                FROM T_user_cache 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            data = await cur.fetchone()
            if data and data[0]:
                result = json.loads(data[0])
            return JSONResponse.success(result)
        
    @ExceptionLogger.handle_database_exception_async
    async def get_user_config(account_id: int):
        async with MySQLManager.read_only_cursor() as cur:
            sql = """
                SELECT 
                    user_level, 
                    storage_limit 
                FROM T_user_config 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            data = await cur.fetchone()
            if data is None:
                raise DataIntegrityError(account_id)
            else:
                return JSONResponse.success(data)
            
    @ExceptionLogger.handle_database_exception_async
    async def del_user_data(account_id: int):
        """清除用户数据"""
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                UPDATE T_user_stats 
                SET 
                    is_enabled = 0, 
                    is_public = 0, 
                    activity_level = 0, 
                    total_battles = 0, 
                    pve_battles = 0, 
                    pvp_battles = 0, 
                    ranked_battles = 0,
                    rating_battles = 0,
                    karma = 0,
                    last_battle_at = NULL, 
                    next_refresh_at = NULL, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            sql = """
                UPDATE T_user_config 
                SET 
                    user_level = 0, 
                    storage_limit = 0, 
                    query_count = 0, 
                    last_query_at = NULL, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            sql = """
                UPDATE T_user_cache 
                SET 
                    is_due = 0, 
                    ships = 0, 
                    cache = NULL, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            sql = """
                UPDATE T_user_random 
                SET 
                    battles = 0, 
                    total_exp = 0, 
                    win_rate = 0, 
                    avg_damage = 0, 
                    avg_frags = 0, 
                    avg_exp = 0, 
                    max_exp = 0, 
                    max_frags = 0, 
                    max_planes = 0, 
                    max_damage = 0, 
                    max_scouting = 0, 
                    max_potential = 0, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            sql = """
                UPDATE T_user_ranked 
                SET 
                    battles = 0, 
                    total_exp = 0, 
                    win_rate = 0, 
                    avg_damage = 0, 
                    avg_frags = 0, 
                    avg_exp = 0, 
                    max_exp = 0, 
                    max_frags = 0, 
                    max_planes = 0, 
                    max_damage = 0, 
                    max_scouting = 0, 
                    max_potential = 0, 
                    updated_at = NOW() 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            return JSONResponse.API_1000_Success