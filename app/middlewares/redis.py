import json
import asyncio
from typing import Optional
import redis.asyncio as redis
from redis.asyncio.client import Redis

from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.core import EnvConfig, api_logger


class RedisConnection:
    '''管理Redis连接'''
    _conn: Optional[Redis] = None

    @staticmethod
    def _build_redis_url() -> str:
        """构建Redis连接URL"""
        config = EnvConfig.get_config()
        return (
            f"redis://:{config.REDIS.password}"
            f"@{config.REDIS.host}"
            f":{config.REDIS.port}"
            f"/{config.REDIS.db}"
        )

    @classmethod
    async def init_conn(cls) -> Redis:
        """应用启动时调用，初始化Redis连接"""
        if EnvConfig.DEV_MODE:
            api_logger.info("DEV_MODE on, skip Redis connection")
            return
        
        try:
            redis_url = cls._build_redis_url()
            cls._conn = redis.from_url(
                url=redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            api_logger.info("Redis connection initialized successfully")
        except Exception as e:
            api_logger.error(f"Failed to initialize Redis connection: {e}")
            raise

    @classmethod
    async def test_redis(cls) -> None:
        """测试Redis连接"""
        if EnvConfig.DEV_MODE:
            return
        
        try:
            conn = cls.acquire_conn()
            ping_response = await conn.ping()
            if ping_response:
                info = await conn.info("server") # type: dict
                api_logger.info(f"Redis version: {info.get('redis_version', 'unknown')}")
                api_logger.info(f"Redis mode: {info.get('redis_mode', 'unknown').upper()}")
            else:
                api_logger.warning(f"Redis ping failed: {ping_response}")
        except Exception as e:
            api_logger.warning(f"Test Redis connection failed: {e}")

    @classmethod
    async def load_state(cls) -> bool:
        """加载APP当前状态"""
        if EnvConfig.DEV_MODE:
            return True
        
        try:
            key = 'status:maintenance'
            conn = cls.acquire_conn()
            response = await conn.exists(key)
            if response:
                return False
            else: 
                return True
        except Exception as e:
            api_logger.warning(f"Test Redis connection failed: {e}")
            return False

    @classmethod
    async def close_redis(cls) -> None:
        """关闭Redis连接"""
        if cls._conn is None:
            api_logger.info("Redis connection is already closed or not initialized")
            return
        
        try:
            await cls._conn.close()
            api_logger.info("Redis connection closed")
        except Exception as e:
            api_logger.error(f"Failed to close Redis connection: {e}")
        finally:
            cls._conn = None

    @classmethod
    def acquire_conn(cls) -> Redis:
        """获取Redis连接"""
        if cls._conn is None:
            raise RuntimeError("Redis connection is not initialized")
        return cls._conn

class ServiceMetrics:
    @ExceptionLogger.handle_cache_exception_async
    async def api_incr(date: str):
        if EnvConfig.DEV_MODE:
            return
        
        keys = [
            f"metrics:api:annual:{date[:4]}",
            f"metrics:api:monthly:{date[:7]}",
            f"metrics:api:daily:{date}"
        ]
        conn = RedisConnection.acquire_conn()
        for key in keys:
            await conn.incr(key)

    @ExceptionLogger.handle_cache_exception_async
    async def http_incrby(date: str, amount: int):
        if EnvConfig.DEV_MODE:
            return
        
        keys = [
            f"metrics:http:annual:{date[:4]}",
            f"metrics:http:monthly:{date[:7]}",
            f"metrics:http:daily:total:{date}"
        ]
        conn = RedisConnection.acquire_conn()
        for key in keys:
            await conn.incrby(key, amount)

    @ExceptionLogger.handle_cache_exception_async
    async def http_error_incrby(date: str, amount: int):
        if EnvConfig.DEV_MODE:
            return
        key = f"metrics:http:daily:error:{date}"
        conn = RedisConnection.acquire_conn()
        await conn.incrby(key, amount)

class RedisClient:
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def get(key: str) -> dict:
        conn = RedisConnection.acquire_conn()
        data = await conn.get(key)
        if data:
            data = json.loads(data)
        return JSONResponse.success(data)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def get_token(key: str) -> dict:
        conn = RedisConnection.acquire_conn()
        data = await conn.get(key)
        return JSONResponse.success(data)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def get_by_pipe(keys: list) -> dict:
        """用于统计api相关指标"""
        conn = RedisConnection.acquire_conn()
        data = []
        pipe = conn.pipeline()
        for key in keys:
            pipe.get(key)
        values = await pipe.execute()
        for v in values:
            data.append(int(v) if v else 0)
        return JSONResponse.success(data)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def incr(key: str) -> None:
        conn = RedisConnection.acquire_conn()
        await conn.incr(key)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def incrby(key: str, amount: int) -> None:
        conn = RedisConnection.acquire_conn()
        await conn.incrby(key, amount)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def exists(key: str) -> dict:
        conn = RedisConnection.acquire_conn()
        data = await conn.exists(key)
        return JSONResponse.success(data)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def drop(key: str) -> dict:
        conn = RedisConnection.acquire_conn()
        await conn.delete(key)
        return JSONResponse.API_1000_Success

    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def set(key: str, value: dict, ex: int = None):
        conn = RedisConnection.acquire_conn()
        await conn.set(
            name=key, 
            value=json.dumps(value, ensure_ascii=False),
            ex=ex
        )
        return JSONResponse.API_1000_Success

    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def setnx(key: str, value: dict, nx: bool = False, ex: int = None):
        conn = RedisConnection.acquire_conn()
        data = await conn.set(
            name=key, 
            value=json.dumps(value, ensure_ascii=False),
            nx=nx,
            ex=ex
        )
        return JSONResponse.success(data)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def acquire_lock(key: str, ex: int = 5, max_retries: int = 5, intervel: float = 0.2):
        conn = RedisConnection.acquire_conn()
        for _ in range(1, max_retries + 1):
            acquired = await conn.set(
                key, 1, nx=True, ex=ex
            )

            if acquired:
                return JSONResponse.success(True)

            await asyncio.sleep(intervel)
        return JSONResponse.success(False)

    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def zget_top_n(key: str, n: int = 50):
        conn = RedisConnection.acquire_conn()
        if n <= 0:
            return []
        # 索引从0开始，所以前N个的结束索引是 n-1
        data = await conn.zrevrange(key, 0, n - 1)
        return JSONResponse.success(data)

    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def zget_range(key: str, start: int, stop: int):
        conn = RedisConnection.acquire_conn()
        data = await conn.zrevrange(key, start, stop)
        return JSONResponse.success(data)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def zget_total(key: str):
        """获取有序集合中的成员总数"""
        conn = RedisConnection.acquire_conn()
        data = await conn.zcard(key)
        count = int(data) if data else 0
        return JSONResponse.success(count)

    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def zget_rank(key: str, member: str):
        conn = RedisConnection.acquire_conn()
        data = await conn.zrevrank(key, member)
        return JSONResponse.success(data)
    
    @staticmethod
    @ExceptionLogger.handle_cache_exception_async
    async def zrem_member(keys: list, member: str):
        """从多个 ZSET key 中删除同一个 member"""
        conn = RedisConnection.acquire_conn()
        pipe = conn.pipeline()
        for key in keys:
            pipe.zrem(key, member)
        results = await pipe.execute()
        return JSONResponse.success(results)

