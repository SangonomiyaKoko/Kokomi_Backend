from aiomysql.connection import Connection
from aiomysql.cursors import Cursor

from app.database import MysqlConnection
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.utils import GameUtils, TimeUtils
from app.constants import Limits


class BotUserModel:
    @ExceptionLogger.handle_database_exception_async
    async def get_user_bind(platform: str, platform_user_id: str):
        '''
        从数据库中读取用户的绑定的账号

        参数:
            platform: 平台(qq/qq_group/qq_guild/wechat/discord)
            user_id: 用户id
        '''
        try:
            connection: Connection = await MysqlConnection.get_connection()
            await connection.begin()
            cursor: Cursor = await connection.cursor()

            platform_id = GameUtils.get_platform_id(platform) 
            sql = """
                SELECT 
                    current_id 
                FROM bind_idx 
                WHERE platform_id = %s 
                  AND platform_user_id = %s;
            """
            await cursor.execute(
                sql,[platform_id, platform_user_id]
            )
            user = await cursor.fetchone()
            if user and user[0] != None:
                current_id = user[0]
                sql = """
                    SELECT 
                        region_id, 
                        account_id, 
                        username, 
                        UNIX_TIMESTAMP(register_time), 
                        insignias 
                    FROM user_base 
                    WHERE id = %s;
                """
                await cursor.execute(
                    sql,[current_id]
                )
                result = await cursor.fetchone()
                if result is None:
                    # 正常来说，用户绑定后该账号数据一定存在于数据库
                    # 但是保险起见，还是在此抛出error
                    return JSONResponse.get_error_response(
                        code=4104,
                        message='MySQLDataNotFoundError'
                    )
                else:
                    data = {
                        'region': GameUtils.get_region(result[0]),
                        'account_id': result[1],
                        'username': result[2],
                        'register_time': result[3],
                        'insignias': result[4]
                    }
            else:
                data = None

            await connection.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await connection.rollback()
            raise e
        finally:
            await cursor.close()
            await MysqlConnection.release_connection(connection)
    
    @ExceptionLogger.handle_database_exception_async
    async def get_user_bind_list(platform: str, platform_user_id: str):
        '''
        从数据库中读取用户的绑定的账号列表

        参数:
            platform: 平台
            platform_user_id: 用户id
        '''
        try:
            connection: Connection = await MysqlConnection.get_connection()
            await connection.begin()
            cursor: Cursor = await connection.cursor()

            platform_id = GameUtils.get_platform_id(platform) 
            # 获取当前绑定索引
            sql = """
                SELECT 
                    id, 
                    current_id 
                FROM bind_idx 
                WHERE platform_id = %s 
                  AND platform_user_id = %s;
            """
            await cursor.execute(
                sql,[platform_id, platform_user_id]
            )
            user = await cursor.fetchone()
            if user:
                # 读取绑定列表数据
                sql = """
                    SELECT 
                        l.game_id, 
                        b.region_id, 
                        b.account_id, 
                        b.username, 
                        UNIX_TIMESTAMP(b.register_time), 
                        b.insignias 
                    FROM bind_list AS l 
                    LEFT JOIN user_base AS b 
                        ON b.id = l.game_id 
                    WHERE l.user_id = %s 
                    ORDER BY l.created_at;
                """
                await cursor.execute(
                    sql,[user[0]]
                )
                result = await cursor.fetchall()
                if result:
                    data = []
                    for bind_data in result:
                        data.append(
                            {
                                'region': GameUtils.get_region(bind_data[1]),
                                'acoount_id': bind_data[2],
                                'username': bind_data[3],
                                'register_time': bind_data[4],
                                'insignias': bind_data[5],
                                'is_cunrrent': 1 if bind_data[0] == user[1] else 0
                            }
                        )
            else:
                data = None

            await connection.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await connection.rollback()
            raise e
        finally:
            await cursor.close()
            await MysqlConnection.release_connection(connection)

    @ExceptionLogger.handle_database_exception_async
    async def del_user_bind(platform: str, platform_user_id: str, del_index: int):
        '''
        读取绑定列表并删除指定索引的数据

        参数:
            platform: 平台
            platform_user_id: 用户id
        '''
        try:
            connection: Connection = await MysqlConnection.get_connection()
            await connection.begin()
            cursor: Cursor = await connection.cursor()

            platform_id = GameUtils.get_platform_id(platform) 
            # 获取当前绑定索引
            sql = """
                SELECT 
                    id, 
                    current_id 
                FROM bind_idx 
                WHERE platform_id = %s 
                  AND platform_user_id = %s;
            """
            await cursor.execute(
                sql,[platform_id, platform_user_id]
            )
            user = await cursor.fetchone()
            if user:
                # 读取绑定列表数据
                sql = """
                    SELECT 
                        game_id 
                    FROM bind_list 
                    WHERE user_id = %s 
                    ORDER BY created_at;
                """
                await cursor.execute(
                    sql,[user[0]]
                )
                result = await cursor.fetchall()
            else:
                result = None
            # 没有绑定数据
            if result is None:
                await connection.commit()
                return JSONResponse.API_2010_NoBindingData
            # 索引越界
            if del_index > len(result):
                await connection.commit()
                return JSONResponse.API_2011_BindingIndexOutOfRange
            del_game_id = result[del_index - 1][0]
            # 删除绑定记录
            sql = """
                DELETE FROM bind_list 
                WHERE user_id = %s 
                  AND game_id = %s;
            """
            await cursor.execute(
                sql,[user[0], del_game_id]
            )
            # 判断删除的账号是否为当前绑定账号
            if del_game_id == user[1]:
                sql = """
                    UPDATE bind_idx 
                    SET 
                        current_id = NULL 
                    WHERE platform_id = %s 
                      AND platform_user_id = %s;
                """
                await cursor.execute(
                    sql,[platform_id, platform_user_id]
                )
                await connection.commit()
                return JSONResponse.API_2012_CurrentBindingBeDeleted

            await connection.commit()
            return JSONResponse.API_1000_Success
        except Exception as e:
            await connection.rollback()
            raise e
        finally:
            await cursor.close()
            await MysqlConnection.release_connection(connection)

    @ExceptionLogger.handle_program_exception_async
    async def switch_user_bind(platform: str, platform_user_id: str, switch_index: int):
        '''
        读取绑定列表并切换绑定账号

        参数:
            platform: 平台
            platform_user_id: 用户id
        '''
        try:
            connection: Connection = await MysqlConnection.get_connection()
            await connection.begin()
            cursor: Cursor = await connection.cursor()

            platform_id = GameUtils.get_platform_id(platform) 
            # 获取当前绑定索引
            sql = """
                SELECT 
                    id, 
                    current_id 
                FROM bind_idx 
                WHERE platform_id = %s 
                  AND platform_user_id = %s;
            """
            await cursor.execute(
                sql,[platform_id, platform_user_id]
            )
            user = await cursor.fetchone()
            if user:
                # 读取绑定列表数据
                sql = """
                    SELECT 
                        l.game_id, 
                        b.region_id, 
                        b.account_id, 
                        b.username, 
                        UNIX_TIMESTAMP(b.register_time), 
                        b.insignias 
                    FROM bind_list AS l 
                    LEFT JOIN user_base AS b 
                        ON b.id = l.game_id 
                    WHERE l.user_id = %s 
                    ORDER BY l.created_at;
                """
                await cursor.execute(
                    sql,[user[0]]
                )
                result = await cursor.fetchall()
            else:
                result = None
            # 没有绑定数据
            if result is None:
                await connection.commit()
                return JSONResponse.API_2010_NoBindingData
            if switch_index > len(result):
                await connection.commit()
                return JSONResponse.API_2011_BindingIndexOutOfRange
            switch_data = result[switch_index-1]
            game_id = switch_data[0]
            sql = """
                UPDATE bind_idx 
                SET 
                    current_id = %s 
                WHERE platform_id = %s 
                    AND platform_user_id = %s;
            """
            await cursor.execute(
                sql,[game_id, platform_id, platform_user_id]
            )
            data = {
                "region": GameUtils.get_region(switch_data[1]),
                "account_id": switch_data[2],
                "username": switch_data[3],
                "register_time": switch_data[4],
                "insignias": switch_data[5]
            }

            await connection.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await connection.rollback()
            raise e
        finally:
            await cursor.close()
            await MysqlConnection.release_connection(connection)

    @ExceptionLogger.handle_database_exception_async
    async def post_user_bind(platform: str, platform_user_id: str, region_id: int, account_id: int):
        '''
        从数据库中读取用户的绑定的账号

        参数:
            platform: 平台(qq/qq_group/qq_guild/wechat/discord)
            user_id: 用户id
        '''
        try:
            connection: Connection = await MysqlConnection.get_connection()
            await connection.begin()
            cursor: Cursor = await connection.cursor()

            # 读取当前用户id和当前绑定id
            platform_id = GameUtils.get_platform_id(platform)
            sql = """
                SELECT 
                    id, 
                    current_id 
                FROM bind_idx 
                WHERE platform_id = %s 
                  AND platform_user_id = %s;
            """
            await cursor.execute(
                sql,[platform_id, platform_user_id]
            )
            result = await cursor.fetchone()
            if result is None:
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
                        id 
                    FROM bind_idx 
                    WHERE platform_id = %s 
                    AND platform_user_id = %s;
                """
                await cursor.execute(
                    sql,[platform_id, platform_user_id]
                )
                result = await cursor.fetchone()
                user_id = result[0]
                current_id = None
            else:
                user_id = result[0]
                current_id = result[1]
            sql = """
                SELECT 
                    id 
                FROM user_base 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cursor.execute(
                sql,[region_id, account_id]
            )
            result = await cursor.fetchone()
            if result is None:
                # 获取id失败，提前退出
                await connection.commit()
                return JSONResponse.get_error_response(
                    code=4104,
                    message='MySQLDataNotFoundError'
                )
            game_id = result[0]
            # 判断是否进行绑定数据的写入
            data = JSONResponse.API_1000_Success
            if current_id != game_id:
                sql = """
                    SELECT 
                        COUNT(*) 
                    FROM bind_list 
                    WHERE user_id = %s;
                """
                await cursor.execute(
                    sql,[user_id]
                )
                result = await cursor.fetchone()
                if result[0] >= Limits.MaxBindingLimit:
                    # 到达最大绑定数量
                    data = JSONResponse.API_2009_MaxBindingLimitReached
                else:
                    sql = """
                        SELECT 
                            EXISTS (
                                SELECT 
                                    1 
                                FROM bind_list 
                                WHERE user_id = %s 
                                  AND game_id = %s
                            ) AS is_exists;
                    """
                    await cursor.execute(
                        sql,[user_id, game_id]
                    )
                    result = await cursor.fetchone()
                    if result[0] == 0:
                        sql = """
                            INSERT INTO bind_list (
                                user_id, 
                                game_id
                            ) VALUE (
                                %s, %s
                            );
                        """
                        await cursor.execute(
                            sql,[user_id, game_id]
                        )
                    sql = """
                        UPDATE bind_idx 
                        SET 
                            current_id = %s 
                        WHERE platform_id = %s 
                            AND platform_user_id = %s;
                    """
                    await cursor.execute(
                        sql,[game_id, platform_id, platform_user_id]
                    )

            await connection.commit()
            return data
        except Exception as e:
            await connection.rollback()
            raise e
        finally:
            await cursor.close()
            await MysqlConnection.release_connection(connection)

    @ExceptionLogger.handle_database_exception_async
    async def premium_status(platform: str, platform_user_id: str):
        '''
        从数据库中读取用户的会员信息

        参数:
            platform: 平台(qq/qq_group/qq_guild/wechat/discord)
            user_id: 用户id
        '''
        try:
            connection: Connection = await MysqlConnection.get_connection()
            await connection.begin()
            cursor: Cursor = await connection.cursor()

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
                await connection.commit()
                return JSONResponse.MySQL_4104_DataNotFoundError
            if user[1] and user[1] > TimeUtils.timestamp():
                user_id = user[0]
                sql = """
                    SELECT game_id 
                    FROM recent_pro 
                    WHERE user_id = %s;
                """
                await cursor.execute(sql,[user_id])
                game_users = await cursor.fetchall()
                if len(game_users) == 0:
                    data = {
                        'id': user_id,
                        'expired_at': user[1],
                        'level': user[2],
                        'limit': user[3],
                        'users': []
                    }
                else:
                    placeholders = ",".join(["%s"] * len(game_users))
                    sql = f"""
                        SELECT 
                            region_id, 
                            account_id, 
                            username 
                        FROM user_base 
                        WHERE id IN ({placeholders});
                    """
                    await cursor.execute(sql,[x[0] for x in game_users])
                    users = await cursor.fetchall()
                    data = {
                        'id': user_id,
                        'expired_at': user[1],
                        'level': user[2],
                        'limit': user[3],
                        'users': users
                    }
            else:
                data = None

            await connection.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await connection.rollback()
            raise e
        finally:
            await cursor.close()
            await MysqlConnection.release_connection(connection)