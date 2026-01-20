from aiomysql.connection import Connection
from aiomysql.cursors import Cursor

from app.database import MysqlConnection
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.utils import GameUtils


class GameModel:
    @ExceptionLogger.handle_database_exception_async
    async def get_game_version(region: str):
        '''
        获取数据库中存储的游戏版本
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            region_id = GameUtils.get_region_id(region)
            data = {
                'version': None
            }
            sql = """
                SELECT 
                    short_version 
                FROM region_version 
                WHERE region_id = %s;
            """
            await cur.execute(sql,[region_id])
            game = await cur.fetchone()
            data['version'] = game[0]

            await conn.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)

    @ExceptionLogger.handle_database_exception_async
    async def update_game_version(region: str, game_version: str):
        '''
        更新数据库中存储的游戏版本
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            region_id = GameUtils.get_region_id(region)
            version = ".".join(game_version.split(".")[:2])
            sql = """
                SELECT 
                    short_version 
                FROM region_version 
                WHERE region_id = %s;
            """
            await cur.execute(
                sql,[region_id]
            )
            row = await cur.fetchone()
            if row[0] != version:
                sql = """
                    UPDATE region_version 
                    SET 
                        short_version = %s, 
                        version_start = CURRENT_TIMESTAMP, 
                        full_version = %s 
                    WHERE region_id = %s;
                """
                await cur.execute(
                    sql,[version, game_version, region_id]
                )
            else:
                sql = """
                    UPDATE region_version 
                    SET 
                        full_version = %s 
                    WHERE region_id = %s;
                """
                await cur.execute(
                    sql,[game_version, region_id]
                )

            await conn.commit()
            return JSONResponse.API_1000_Success
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)