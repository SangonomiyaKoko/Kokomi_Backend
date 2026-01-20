from aiomysql.connection import Connection
from aiomysql.cursors import Cursor

from app.database import MysqlConnection
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.utils import StringUtils, GameUtils, TimeUtils


class PremiumModel:
    @ExceptionLogger.handle_database_exception_async
    async def generate_code(max_use: int, validity: int, level: int, limit: int, describe: str = None):
        try:
            connection: Connection = await MysqlConnection.get_connection()
            await connection.begin()
            cursor: Cursor = await connection.cursor()

            code = StringUtils.generate_activation_code()
            sql = """
                SELECT 
                    1 
                FROM activation_codes 
                WHERE code = %s 
                LIMIT 1;
            """
            await cursor.execute(sql,[code])
            data = await cursor.fetchone()
            if data != None:
                await connection.commit()
                return JSONResponse.API_2022_ActivationCodeGenerationFailed
            sql = """
                INSERT INTO activation_codes (
                    code, 
                    max_use, 
                    used_count, 
                    validity, 
                    premium_level, 
                    recent_limit, 
                    code_describe
                ) VALUE (
                    %s,%s,%s,%s,%s,%s,%s
                );
            """
            await cursor.execute(sql,[code,max_use,0,validity,level,limit,describe if describe else None])

            await connection.commit()
            return JSONResponse.get_success_response(code)
        except Exception as e:
            await connection.rollback()
            raise e
        finally:
            await cursor.close()
            await MysqlConnection.release_connection(connection)

    @ExceptionLogger.handle_database_exception_async
    async def use_code(platform: str, platform_user_id: str, code: str):
        try:
            connection: Connection = await MysqlConnection.get_connection()
            await connection.begin()
            cursor: Cursor = await connection.cursor()

            # 先读取用户的绑定数据
            platform_id = GameUtils.get_platform_id(platform) 
            sql = """
                SELECT 
                    id, 
                    UNIX_TIMESTAMP(premium_expired_at), 
                    premium_level, 
                    premium_limit 
                FROM bind_idx 
                WHERE platform_id = %s 
                  AND platform_user_id = %s;
            """
            await cursor.execute(
                sql,[platform_id, platform_user_id]
            )
            user = await cursor.fetchone()
            if user is None:
                sql = """
                    INSERT INTO bind_idx (
                        platform_id, 
                        platform_user_id
                    ) VALUE (
                        %s, %s
                    );
                """
                await cursor.execute(
                    sql,[platform_id, platform_user_id]
                )
                sql = """
                    SELECT 
                        id, 
                        UNIX_TIMESTAMP(premium_expired_at), 
                        premium_level, 
                        premium_limit 
                    FROM bind_idx 
                    WHERE platform_id = %s 
                    AND platform_user_id = %s;
                """
                await cursor.execute(
                    sql,[platform_id, platform_user_id]
                )
                user = await cursor.fetchone()
            user_id = user[0]
            # 读取code对应的数据，检查是否还有效
            sql = """
                SELECT 
                    max_use, 
                    used_count, 
                    validity, 
                    premium_level, 
                    recent_limit 
                FROM activation_codes 
                WHERE code = %s 
                LIMIT 1;
            """
            await cursor.execute(sql,[code])
            data = await cursor.fetchone()
            if data is None or (data[0] <= data[1]):
                await connection.commit()
                return JSONResponse.API_2023_InvalidActivationCode
            sql = """
                SELECT 
                    1 
                FROM user_activation 
                WHERE code = %s 
                  AND user_id = %s;
            """
            await cursor.execute(sql,[code, user_id])
            exists = await cursor.fetchone()
            if exists != None:
                await connection.commit()
                return JSONResponse.API_2024_ActivationCodeAlreadyUsed
            # 使用code
            use_count = data[1] + 1
            now_timestamp = TimeUtils.timestamp()
            if user[1] is None or user[1] <= now_timestamp:
                expired_at = int(now_timestamp+data[2]*24*60*60)
                level = data[3]
                limit = data[4]
            else:
                expired_at = int(user[1]+data[2]*24*60*60)
                level = max(data[3], user[2])
                limit = max(data[4], user[3])
            sql = """
                UPDATE bind_idx 
                SET 
                    premium_expired_at = FROM_UNIXTIME(%s), 
                    premium_level = %s, 
                    premium_limit = %s 
                WHERE platform_id = %s 
                  AND platform_user_id = %s;
            """
            await cursor.execute(sql,[expired_at, level, limit, platform_id, platform_user_id])
            sql = """
                UPDATE activation_codes 
                SET 
                    used_count = %s 
                WHERE code = %s;
            """
            await cursor.execute(sql,[use_count,code])
            sql = """
                INSERT INTO user_activation (
                    code, 
                    user_id
                ) VALUE (
                    %s,%s
                );
            """
            await cursor.execute(sql,[code,user_id])
            result = {
                'expired_at': expired_at,
                'level': level,
                'limit': limit
            }
            
            await connection.commit()
            return JSONResponse.get_success_response(result)
        except Exception as e:
            await connection.rollback()
            raise e
        finally:
            await cursor.close()
            await MysqlConnection.release_connection(connection)