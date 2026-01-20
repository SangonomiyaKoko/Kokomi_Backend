from aiomysql.connection import Connection
from aiomysql.cursors import Cursor

from app.database import MysqlConnection
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.utils import GameUtils
from app.constants import Limits


class RecentModel:
    @ExceptionLogger.handle_database_exception_async
    async def enable_recent(region: str, account_id: int):
        '''
        启用recent(普通)功能
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            region_id = GameUtils.get_region_id(region)
            sql = """
                SELECT 
                    enable_recent, 
                    enable_daily, 
                    recent_limit
                FROM recent 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cur.execute(sql,[region_id,account_id])
            data = await cur.fetchone()
            if data is None:
                sql = """
                    INSERT INTO recent (
                        region_id, 
                        account_id, 
                        enable_recent, 
                        recent_limit
                    ) VALUE (
                        %s,%s,%s,%s
                    );
                """
                await cur.execute(sql,[region_id,account_id,1,Limits.DefaultRecentLimit])
                result = {
                    'type': 'standard',
                    'limit': Limits.DefaultRecentLimit
                }
            else:
                if data[0] == 0:
                    sql = """
                        UPDATE recent 
                        SET 
                            enable_recent = 1, 
                            recent_limit = %s
                        WHERE region_id = %s 
                          AND account_id = %s;
                    """
                    await cur.execute(sql,[Limits.DefaultRecentLimit,region_id,account_id])
                    result = {
                        'type': 'standard',
                        'limit': Limits.DefaultRecentLimit
                    }
                else:
                    result = {
                        'type': 'standard' if data[1] == 0 else 'premium',
                        'limit': data[2]
                    }
            
            await conn.commit()
            return JSONResponse.get_success_response(result)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)
    
    @ExceptionLogger.handle_database_exception_async
    async def enable_recent_pro(region: str, account_id: int, user_id: int, limit: int):
        '''
        启用recent(pro)功能
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            region_id = GameUtils.get_region_id(region)
            sql = """
                SELECT 
                    id 
                FROM user_base 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cur.execute(sql,[region_id,account_id])
            data = await cur.fetchone()
            if data is None:
                return JSONResponse.MySQL_4104_DataNotFoundError
            game_id = data[0]
            sql = """
                SELECT 
                    enable_recent, 
                    enable_daily, 
                    recent_limit 
                FROM recent 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cur.execute(sql,[region_id,account_id])
            data = await cur.fetchone()
            if data is None:
                sql = """
                    INSERT INTO recent (
                        region_id, 
                        account_id, 
                        enable_recent, 
                        enable_daily, 
                        recent_limit 
                    ) VALUE (
                        %s,%s,%s,%s,%s
                    );
                """
                await cur.execute(sql,[region_id,account_id,1,1,limit])
                sql = """
                    INSERT INTO recent_pro (
                        user_id, game_id
                    ) VALUE (
                        %s,%s
                    );
                """
                await cur.execute(sql,[user_id, game_id])
                result = {
                    'type': 'premium',
                    'limit': limit
                }
            else:
                if data[1] == 1:
                    await conn.commit()
                    return JSONResponse.API_2017_FeatureAlreadyEnabled
                if data[0] == 0 or data[1] == 0:
                    sql = """
                        UPDATE recent 
                        SET 
                            enable_recent = 1, 
                            enable_daily = 1, 
                            recent_limit = %s 
                        WHERE region_id = %s 
                          AND account_id = %s;
                    """
                    await cur.execute(sql,[limit,region_id,account_id])
                    sql = """
                        INSERT INTO recent_pro (
                            user_id, game_id
                        ) VALUE (
                            %s,%s
                        );
                    """
                    await cur.execute(sql,[user_id, game_id])
                    result = {
                        'type': 'premium',
                        'limit': limit
                    }
                
            await conn.commit()
            return JSONResponse.get_success_response(result)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)
    
    @ExceptionLogger.handle_database_exception_async
    async def disable_recent_pro(region: str, account_id: int, user_id: int):
        '''
        用户解除recent_pro权限
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            region_id = GameUtils.get_region_id(region)
            sql = """
                SELECT 
                    id 
                FROM user_base 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cur.execute(sql,[region_id,account_id])
            data = await cur.fetchone()
            if data is None:
                return JSONResponse.MySQL_4104_DataNotFoundError
            game_id = data[0]
            sql = """
                UPDATE recent 
                SET 
                    enable_daily = 0 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cur.execute(sql,[region_id,account_id])
            sql = """
                DELETE FROM recent_pro 
                WHERE user_id = %s 
                  AND game_id = %s;
            """
            await cur.execute(sql,[user_id,game_id])

            await conn.commit()
            return JSONResponse.API_1000_Success
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)

    @ExceptionLogger.handle_database_exception_async
    async def del_recent(region: str, account_id: int):
        '''
        [内部方法]删除recent功能
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            region_id = GameUtils.get_region_id(region)
            sql = """
                UPDATE recent 
                SET 
                    enable_recent = 0 
                WHERE region_id = %s 
                    AND account_id = %s;
            """
            await cur.execute(sql,[region_id,account_id])
            
            await conn.commit()
            return JSONResponse.API_1000_Success
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)
    
    @ExceptionLogger.handle_database_exception_async
    async def del_recents(region: str, account_id: int):
        '''
        [内部方法]删除recents功能
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            region_id = GameUtils.get_region_id(region)
            sql = """
                SELECT 
                    id 
                FROM user_base 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cur.execute(sql,[region_id,account_id])
            data = await cur.fetchone()
            if data is None:
                return JSONResponse.MySQL_4104_DataNotFoundError
            game_id = data[0]
            sql = """
                UPDATE recent 
                SET 
                    enable_daily = 0 
                WHERE region_id = %s 
                    AND account_id = %s;
            """
            await cur.execute(sql,[region_id,account_id])
            sql = """
                DELETE FROM recent_pro 
                WHERE game_id = %s;
            """
            await cur.execute(sql,[game_id])
            
            await conn.commit()
            return JSONResponse.API_1000_Success
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)