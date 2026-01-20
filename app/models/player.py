from aiomysql.connection import Connection
from aiomysql.cursors import Cursor

from app.database import MysqlConnection
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.schemas import UserBasicData
from app.utils import GameUtils


class PlatyerModel:

    @ExceptionLogger.handle_database_exception_async
    async def check_base(region_id: int, account_id: int, username: str = None):
        '''
        检查该uid是否存在于数据库中，确保事务正常
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            sql = """
                SELECT 
                    username
                FROM user_base 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cur.execute(
                sql,[region_id, account_id]
            )
            result = await cur.fetchone()
            if result is None:
                default_name = GameUtils.get_user_default_name(account_id)
                sql = """
                    INSERT INTO user_base (
                        region_id, 
                        account_id, 
                        username
                    ) VALUES (
                        %s, %s, %s
                    );
                """
                await cur.execute(
                    sql,[region_id, account_id, default_name]
                )
                sql = """
                    INSERT INTO user_stats (
                        account_id
                    ) VALUES (
                        %s
                    );
                """
                await cur.execute(
                    sql,[account_id]
                )
                sql = """
                    INSERT INTO user_clan (
                        account_id
                    ) VALUES (
                        %s
                    );
                """
                await cur.execute(
                    sql,[account_id]
                )
                sql = """
                    INSERT INTO user_cache (
                        account_id
                    ) VALUES (
                        %s
                    );
                """
                await cur.execute(
                    sql,[account_id]
                )
                result = [default_name, None]
                if username:
                    sql = """
                        UPDATE user_base 
                        SET 
                            username = %s
                        WHERE region_id = %s 
                          AND account_id = %s;
                    """
                    await cur.execute(
                        sql,[username, region_id, account_id]
                    )

            await conn.commit()
            return JSONResponse.API_1000_Success
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)

    @ExceptionLogger.handle_database_exception_async
    async def get_user_brief(region_id: int, account_id: int):
        '''
        从数据库中获取用户的基本数据，如果玩家或者工会的缓存数据不存在则返回none

        用户数据为空或者隐藏战绩也返回none

        参数：
            account_id: 用户id
            region_id: 服务器id
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            data = {
                'region': GameUtils.get_region(region_id),
                'account_id': account_id,
                'username': None,
                'register_time': None,
                'insignias': None,
                'clan_id': None,
                'clan_tag': None,
                'clan_league': None
            }
            # 从数据库中读取缓存数据
            sql = """
                SELECT 
                    b.username, 
                    UNIX_TIMESTAMP(b.register_time) AS register_time, 
                    b.insignias, 
                    UNIX_TIMESTAMP(b.touch_at) AS name_touch_time, 
                    i.is_enabled, 
                    i.is_public, 
                    UNIX_TIMESTAMP(i.touch_at) AS info_touch_time 
                FROM user_base as b 
                LEFT JOIN user_stats as i 
                  ON b.account_id = i.account_id 
                WHERE b.region_id = %s 
                  AND b.account_id = %s;
            """
            await cur.execute(
                sql,[region_id, account_id]
            )
            result = await cur.fetchone()
            # 用户在数据库中不存在或者没有缓存数据
            if (
                result is None or 
                result[3] is None or 
                result[4] == 0 or 
                result[5] == 0 or 
                result[6] is None
            ):
                data = None
            else:
                data['username'] = result[0]
                data['register_time'] = result[1]
                data['insignias'] = result[2]
                sql = """
                    SELECT 
                        clan_id, 
                        UNIX_TIMESTAMP(touch_at) 
                    FROM user_clan 
                    WHERE account_id = %s;
                """
                await cur.execute(
                    sql,[account_id]
                )
                result = await cur.fetchone()
                # 所在工会缓存数据不存在
                if result[1] is None:
                    data = None
                elif result[0] != None:
                    data['clan_id'] = result[0]
                    sql = """
                        SELECT 
                            tag, 
                            league 
                        FROM clan_base 
                        WHERE region_id = %s 
                          AND clan_id = %s;
                    """
                    await cur.execute(
                        sql,[region_id, result[0]]
                    )
                    result = await cur.fetchone()
                    # 判断工会数据是否在数据库中
                    if result != None:
                        data['clan_tag'] = result[0]
                        data['clan_league'] = result[1]
                    else:
                        data = None

            await conn.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)

    @ExceptionLogger.handle_database_exception_async
    async def refresh_base(data: UserBasicData):
        '''
        根据api请求获取到的用户和用户所在工会数据刷新数据库数据
        '''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            # 先处理更新user_base user_basic user_clan的用户数据
            sql = """
                SELECT 
                    username, 
                    UNIX_TIMESTAMP(register_time), 
                    insignias 
                FROM user_base 
                WHERE region_id = %s 
                  AND account_id = %s;
            """
            await cur.execute(
                sql,[data.region_id, data.account_id]
            )
            result = await cur.fetchone()
            if result is None:
                default_name = GameUtils.get_user_default_name(data.account_id)
                sql = """
                    INSERT INTO user_base (
                        region_id, 
                        account_id, 
                        username
                    ) VALUES (
                        %s, %s, %s
                    );
                """
                await cur.execute(
                    sql,[data.region_id, data.account_id, default_name]
                )
                sql = """
                    INSERT INTO user_stats (
                        account_id
                    ) VALUES (
                        %s
                    );
                """
                await cur.execute(
                    sql,[data.account_id]
                )
                sql = """
                    INSERT INTO user_clan (
                        account_id
                    ) VALUES (
                        %s
                    );
                """
                await cur.execute(
                    sql,[data.account_id]
                )
                sql = """
                    INSERT INTO user_cache (
                        account_id
                    ) VALUES (
                        %s
                    );
                """
                await cur.execute(
                    sql,[data.account_id]
                )
                result = [default_name, None]
            if data.is_enabled == 0:
                sql = """
                    UPDATE user_stats 
                    SET 
                        is_enabled = %s, 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id = %s;
                """
                await cur.execute(
                    sql,[data.is_enabled, data.account_id]
                )
            elif data.is_public == 0:
                if result[0] != data.username:
                    sql = """
                        UPDATE user_base 
                        SET 
                            username = %s, 
                            touch_at = CURRENT_TIMESTAMP 
                        WHERE region_id = %s 
                          AND account_id = %s;
                    """
                    await cur.execute(
                        sql,[data.username, data.region_id, data.account_id]
                    )
                sql = """
                    UPDATE user_stats 
                    SET 
                        is_enabled = %s, 
                        activity_level = %s, 
                        is_public = %s, 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id = %s;
                """
                await cur.execute(
                    sql,[data.is_enabled, data.activity_level, data.is_public, data.account_id]
                )
            else:
                if result[0] != data.username or result[1] != data.register_time or result[2] != data.insignias:
                    sql = """
                        UPDATE user_base 
                        SET 
                            username = %s, 
                            register_time = FROM_UNIXTIME(%s), 
                            insignias = %s, 
                            touch_at = CURRENT_TIMESTAMP 
                        WHERE region_id = %s 
                          AND account_id = %s;
                    """
                    await cur.execute(
                        sql,[data.username, data.register_time, data.insignias, data.region_id, data.account_id]
                    )
                else:
                    sql = """
                        UPDATE user_base 
                        SET 
                            insignias = %s, 
                            touch_at = CURRENT_TIMESTAMP 
                        WHERE region_id = %s 
                          AND account_id = %s;
                    """
                    await cur.execute(
                        sql,[data.insignias, data.region_id, data.account_id]
                    )
                sql = """
                    UPDATE user_stats 
                    SET 
                        is_enabled = %s, 
                        activity_level = %s, 
                        is_public = %s, 
                        total_battles = %s, 
                        pvp_battles = %s, 
                        ranked_battles = %s, 
                        last_battle_at = FROM_UNIXTIME(%s), 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id = %s;
                """
                await cur.execute(
                    sql,
                    [
                        data.is_enabled, data.activity_level, data.is_public, data.total_battles, data.pvp_battles,
                        data.ranked_battles, data.last_battle_at, data.account_id
                    ]
                )
            # 处理更新clan_base数据
            if data.clan != None and data.clan.clan_id == None:
                sql = """
                    UPDATE user_clan 
                    SET 
                        clan_id = %s, 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id = %s;
                """
                await cur.execute(
                    sql,[data.clan.clan_id, data.account_id]
                )
            elif data.clan != None and data.clan.clan_id != None:
                sql = """
                    SELECT 
                        tag, 
                        league 
                    FROM clan_base 
                    WHERE region_id = %s 
                      AND clan_id = %s;
                """
                await cur.execute(
                    sql,[data.region_id, data.clan.clan_id]
                )
                result = await cur.fetchone()
                if result is None:
                    default_name = GameUtils.get_clan_default_name()
                    sql = """
                        INSERT INTO clan_base (
                            region_id, 
                            clan_id, 
                            tag
                        ) VALUES (
                            %s, %s, %s
                        );
                    """
                    await cur.execute(
                        sql,[data.region_id, data.clan.clan_id, default_name]
                    )
                    sql = """
                        INSERT INTO clan_stats (
                            clan_id 
                        ) VALUES (
                            %s
                        );
                    """
                    await cur.execute(
                        sql,[data.clan.clan_id]
                    )
                    result = [default_name, None]
                sql = """
                    UPDATE user_clan 
                    SET 
                        clan_id = %s, 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id = %s;
                """
                await cur.execute(
                    sql,[data.clan.clan_id, data.account_id]
                )
                if result[0] != data.clan.tag or result[1] != data.clan.league:
                    sql = """
                        UPDATE clan_base 
                        SET 
                            tag = %s, 
                            league = %s, 
                            touch_at = CURRENT_TIMESTAMP 
                        WHERE region_id = %s 
                          AND clan_id = %s;
                    """
                    await cur.execute(
                        sql,[data.clan.tag, data.clan.league, data.region_id, data.clan.clan_id]
                    )

            await conn.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)