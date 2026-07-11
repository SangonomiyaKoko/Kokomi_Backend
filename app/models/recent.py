from app.database import MySQLManager
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.constants import Limits


class DemoRecentModel:
    @ExceptionLogger.handle_database_exception_async
    async def set_recent_level(account_id: int, target_level: int):
        '''[DEMO] 设置用户recent功能级别

        只允许向上升级，数据库level低于目标level时才会修改
        '''
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                SELECT 
                    user_level 
                FROM T_user_config 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            data = await cur.fetchone()
            if data is None:
                return JSONResponse.API_RecentNotEnable
            
            result = False
            # 只允许向上升级
            if data[0] < target_level:
                storage_level = Limits.DefaultRecentLimit if target_level == 1 else Limits.DefaultRecentProLimit
                sql = """
                    UPDATE T_user_config 
                    SET 
                        user_level = %s, 
                        storage_limit = %s
                    WHERE account_id = %s;
                """
                await cur.execute(sql, [target_level, storage_level, account_id])
                result = True
             
            return JSONResponse.success(result)

    @ExceptionLogger.handle_database_exception_async
    async def reduce_recent_level(account_id: int):
        '''[DEMO] 降低用户recent功能级别'''
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                SELECT 
                    user_level 
                FROM T_user_config 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            data = await cur.fetchone()

            result = False
            if data and data[0] == 2:
                sql = """
                    UPDATE T_user_config 
                    SET 
                        user_level = %s, 
                        storage_limit = %s
                    WHERE account_id = %s;
                """
                await cur.execute(sql, [1, Limits.DefaultRecentLimit, account_id])
                result = True
            
            return JSONResponse.success(result)

    @ExceptionLogger.handle_database_exception_async
    async def disable_recent(account_id: int):
        '''[DEMO] 关闭指定用户的记录Recent数据功能'''
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                SELECT 
                    user_level 
                FROM T_user_config 
                WHERE account_id = %s;
            """
            await cur.execute(sql, [account_id])
            data = await cur.fetchone()
            if data is None:
                return JSONResponse.API_RecentNotEnable
            elif data[0] == 0:
                return JSONResponse.API_RecentNotEnable
            else:
                sql = """
                    UPDATE T_user_config 
                    SET 
                        user_level = %s, 
                        storage_limit = %s
                    WHERE account_id = %s;
                """
                await cur.execute(sql, [0, 0, account_id])
                return JSONResponse.API_1000_Success

class RecentModel:
    @ExceptionLogger.handle_database_exception_async
    async def set_bot_recent_level(account_id: int):
        '''设置用户recent启用'''
        async with MySQLManager.auto_transaction_cursor() as cur:
            sql = """
                UPDATE T_user_config 
                SET 
                    user_level = %s, 
                    storage_limit = %s
                WHERE account_id = %s;
            """
            await cur.execute(sql, [2, Limits.DefaultRecentProLimit, account_id])
        
            return JSONResponse.API_1000_Success