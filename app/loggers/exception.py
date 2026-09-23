import uuid
import redis
import httpx
import traceback
import aiomysql
from typing import Optional

from shard import ServicesName, exception_writer

from app.core import EnvConfig
from app.response import JSONResponse
from app.schemas import GameAPIException, DataIntegrityError


def write_exception(
    error_type: str,
    error_name: str,
    error_info: Optional[str] = None,
    error_id: Optional[str] = None
) -> str:
    """写入异常摘要和详细异常日志，返回本次异常的 ID"""
    return exception_writer(
        log_dir=EnvConfig.LOG_DIR,
        client_id=ServicesName.API,
        error_type=error_type,
        error_name=error_name,
        error_info=error_info,
        error_id=error_id
    )


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
                write_exception(
                    error_type = "ProgramError",
                    error_name = type(e).__name__,
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('ProgramError',error_id,type(e).__name__)
        return wrapper
    
    @staticmethod
    def handle_network_exception_async(func):
        "负责异步网络请求 httpx 的异常捕获"
        async def wrapper(*args, **kwargs):
            try:
                result = await func(*args, **kwargs)
                return result
            except httpx.ConnectTimeout:
                return JSONResponse.game_api_failed('HttpxConnectTimeout')
            except httpx.ReadTimeout:
                return JSONResponse.game_api_failed('HttpxReadTimeout')
            except httpx.TimeoutException:
                return JSONResponse.game_api_failed('HttpxTimeoutError')
            except httpx.ConnectError:
                return JSONResponse.game_api_failed('HttpxConnectError')
            except httpx.ReadError:
                return JSONResponse.game_api_failed('HttpxReadError')
            except httpx.HTTPStatusError:
                return JSONResponse.game_api_failed('HttpxHTTPStatusError')
            except GameAPIException:
                return JSONResponse.game_api_failed('GameAPIException')
            except Exception as e:
                error_id = str(uuid.uuid4())
                write_exception(
                    error_type = 'ProgramError',
                    error_name = type(e).__name__,
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('ProgramError',error_id,type(e).__name__)
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
                write_exception(
                    error_type = "DatabaseError",
                    error_name = "MySQLProgrammingError",
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('MySQLError',error_id,'ProgrammingError')
            except aiomysql.OperationalError as e:
                error_id = str(uuid.uuid4())
                write_exception(
                    error_type = "DatabaseError",
                    error_name = "MySQLOperationalError",
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('MySQLError',error_id,'OperationalError')
            except aiomysql.IntegrityError as e:
                error_id = str(uuid.uuid4())
                write_exception(
                    error_type = "DatabaseError",
                    error_name = "MySQLIntegrityError",
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('MySQLError',error_id,'IntegrityError')
            except aiomysql.DatabaseError as e:
                error_id = str(uuid.uuid4())
                write_exception(
                    error_type = "DatabaseError",
                    error_name = "MySQLDatabaseError",
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('MySQLError',error_id,'DatabaseError')
            except DataIntegrityError as e:
                error_id = str(uuid.uuid4())
                write_exception(
                    error_type = 'MySQLError',
                    error_name = e,
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('MySQLError',error_id,'DataIntegrityError')
            except Exception as e:
                error_id = str(uuid.uuid4())
                write_exception(
                    error_type = 'ProgramError',
                    error_name = type(e).__name__,
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('ProgramError',error_id,type(e).__name__)
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
                write_exception(
                    error_type = 'RedisError',
                    error_name = type(e).__name__,
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('RedisError',error_id,type(e).__name__)
            except Exception as e:
                error_id = str(uuid.uuid4())
                write_exception(
                    error_type = 'ProgramError',
                    error_name = type(e).__name__,
                    error_info = traceback.format_exc(),
                    error_id=error_id
                )
                return JSONResponse.exception('ProgramError',error_id,type(e).__name__)
        return wrapper
    