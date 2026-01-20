import uuid
import redis
import traceback
import aiomysql

from .error_log import write_error_info
from app.response import JSONResponse


class ExceptionLogger:
    @staticmethod
    def handle_program_exception_async(func):
        "负责异步程序异常信息的捕获"
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception as e:
                error_id = str(uuid.uuid4())
                write_error_info(
                    error_id = error_id,
                    error_type = 'ProgramError',
                    error_name = str(type(e).__name__),
                    error_args = str(args) + str(kwargs),
                    error_info = traceback.format_exc()
                )
                return JSONResponse.get_error_response(4000,'ProgramError',error_id)
        return wrapper
    
    @staticmethod
    def handle_database_exception_async(func):
        "负责异步数据库 aiomysql 的异常捕获"
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                return result
            except aiomysql.ProgrammingError as e:
                error_id = str(uuid.uuid4())
                write_error_info(
                    error_id = error_id,
                    error_type = "MySQL",
                    error_name = "MySQLProgrammingError",
                    error_args = str(args) + str(kwargs),
                    error_info = f'ERROR_{e.args[0]}\n' + str(e.args[1]) + f'\n{traceback.format_exc()}'
                )
                return JSONResponse.get_error_response(4101,'MySQLProgrammingError',error_id)
            except aiomysql.OperationalError as e:
                error_id = str(uuid.uuid4())
                write_error_info(
                    error_id = error_id,
                    error_type = "MySQL",
                    error_name = "MySQLOperationalError",
                    error_args = str(args) + str(kwargs),
                    error_info = f'ERROR_{e.args[0]}\n' + str(e.args[1]) + f'\n{traceback.format_exc()}'
                )
                return JSONResponse.get_error_response(4102,'MySQLOperationalError',error_id)
            except aiomysql.IntegrityError as e:
                error_id = str(uuid.uuid4())
                write_error_info(
                    error_id = error_id,
                    error_type = "MySQL",
                    error_name = "MySQLIntegrityError",
                    error_args = str(args) + str(kwargs),
                    error_info = f'ERROR_{e.args[0]}\n' + str(e.args[1]) + f'\n{traceback.format_exc()}'
                )
                return JSONResponse.get_error_response(4103,'MySQLIntegrityError',error_id)
            except aiomysql.DatabaseError as e:
                error_id = str(uuid.uuid4())
                write_error_info(
                    error_id = error_id,
                    error_type = "MySQL",
                    error_name = "MySQLDatabaseError",
                    error_args = str(args) + str(kwargs),
                    error_info = f'ERROR_{e.args[0]}\n' + str(e.args[1]) + f'\n{traceback.format_exc()}'
                )
                return JSONResponse.get_error_response(4100,'MySQLDatabaseError',error_id)
            except Exception as e:
                error_id = str(uuid.uuid4())
                write_error_info(
                    error_id = error_id,
                    error_type = 'ProgramError',
                    error_name = str(type(e).__name__),
                    error_info = traceback.format_exc()
                )
                return JSONResponse.get_error_response(4000,'ProgramError',error_id)
        return wrapper
    
    @staticmethod
    def handle_cache_exception_async(func):
        "负责缓存 Redis 的异常捕获"
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                return result
            except redis.RedisError as e:
                error_id = str(uuid.uuid4())
                write_error_info(
                    error_id = error_id,
                    error_type = 'RedisError',
                    error_name = str(type(e).__name__),
                    error_args = str(args) + str(kwargs),
                    error_info = f'\n{traceback.format_exc()}'
                )
                return JSONResponse.get_error_response(4200,'RedisError',error_id)
            except Exception as e:
                error_id = str(uuid.uuid4())
                write_error_info(
                    error_id = error_id,
                    error_type = 'ProgramError',
                    error_name = str(type(e).__name__),
                    error_args = str(args) + str(kwargs),
                    error_info = traceback.format_exc()
                )
                return JSONResponse.get_error_response(4000,'ProgramError',error_id)
        return wrapper
    