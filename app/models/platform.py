from aiomysql.connection import Connection
from aiomysql.cursors import Cursor

from app.database import MysqlConnection
from app.loggers import ExceptionLogger
from app.response import JSONResponse


class PlatformModel:
    '''数据库管理相关的操作'''
    async def get_innodb_trx():
        '''检测数据库是否有未提交的事务'''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            data = []
            sql = """
                SELECT 
                    trx_id, 
                    trx_mysql_thread_id, 
                    trx_started, 
                    trx_state, 
                    trx_query 
                FROM INFORMATION_SCHEMA.INNODB_TRX 
                WHERE trx_state = 'RUNNING';
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            for row in rows:
                data.append({
                    'id': row[0],
                    'thread_id': row[1],
                    'strated': row[2],
                    'state': row[3],
                    'query': row[4]
                })
            
            await conn.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)

    async def kill_trx(thread_id: str):
        '''删除未提交事务的thread_id'''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            await cur.execute(
                "KILL %s;"
                [thread_id]
            )

            await conn.commit()
            return JSONResponse.API_1000_Success
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)

    async def get_innodb_processlist():
        '''获取数据库的连接数'''
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            data = []
            sql = """
                SELECT 
                    * 
                FROM performance_schema.processlist;
            """
            await cur.execute(sql)
            rows = await cur.fetchall()
            for row in rows:
                data.append({
                    'id': row[0],
                    'user': row[1],
                    'host': row[2],
                    'db': row[3],
                    'command': row[4],
                    'time': row[5],
                    'state': row[6],
                    'info': row[7]
                })
            
            await conn.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)

    
    @ExceptionLogger.handle_database_exception_async
    async def get_basic_user_overview():
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            data = {}
            sql = """
                SELECT 
                    region_id, 
                    COUNT(*) AS cnt 
                FROM user_base 
                GROUP BY region_id;
            """
            await cur.execute(sql)
            users = await cur.fetchall()
            total = 0
            for user in users:
                total += user[1]
                data[user[0]] = user[1]
            data[0] = total
            
            await conn.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)

    
    @ExceptionLogger.handle_database_exception_async
    async def get_basic_clan_overview():
        try:
            conn: Connection = await MysqlConnection.get_connection()
            await conn.begin()
            cur: Cursor = await conn.cursor()

            data = {}
            sql = """
                SELECT 
                    region_id, 
                    COUNT(*) AS cnt 
                FROM clan_base 
                GROUP BY region_id;
            """
            await cur.execute(sql)
            users = await cur.fetchall()
            total = 0
            for user in users:
                total += user[1]
                data[user[0]] = user[1]
            data[0] = total
            
            await conn.commit()
            return JSONResponse.get_success_response(data)
        except Exception as e:
            await conn.rollback()
            raise e
        finally:
            await cur.close()
            await MysqlConnection.release_connection(conn)