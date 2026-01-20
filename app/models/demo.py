from aiomysql.connection import Connection
from aiomysql.cursors import Cursor

from app.database import MysqlConnection
from app.loggers import ExceptionLogger
from app.response import JSONResponse


class DemoModel:
    @ExceptionLogger.handle_database_exception_async
    async def demo():
        '''
        函数注释
        '''
        try:
            # 从连接池获取一条连接
            connection: Connection = await MysqlConnection.get_connection()
            # 事务begin
            await connection.begin()
            # 获取cursor
            cursor: Cursor = await connection.cursor()

            # 这里进行数据库读写操作
            # 这里指定数据库的原因是主要业务数据库和缓存数据库不在一个库内
            sql = """
                SELECT 
                    * 
                FROM user_base 
                WHERE id = %s;
            """
            # 执行
            await cursor.execute(
                sql,[1]
            )
            user = await cursor.fetchone()
            if user:
                data = user[0]
            else:
                data = None

            # 事务commit
            await connection.commit()
            # 返回结果
            return JSONResponse.get_success_response(data)
        except Exception as e:
            # 事务回滚
            await connection.rollback()
            # 向装饰器抛出异常，将会被上层的handle_database_exception_async捕获
            raise e
        finally:
            # 释放资源和连接
            await cursor.close()
            await MysqlConnection.release_connection(connection)