from contextlib import asynccontextmanager

from app.response import JSONResponse
from app.middlewares import RedisClient

@asynccontextmanager
async def recent_refresh_lock(account_id: str):
    """分布式锁上下文管理器"""
    lock_key = f"refresh_lock:recent:{account_id}"
    
    # 尝试获取锁
    error, acquired = JSONResponse.extract_data(
        response=await RedisClient.setnx(lock_key, 1, nx=True, ex=60)
    )
    if error:
        acquired = False
    
    if not acquired:
        yield False
        return
    
    # 获取锁成功
    try:
        yield True
    finally:
        await RedisClient.drop(lock_key)

class UserUpdater:
    """负责维护用户的近期数据库文件，并检查用户是否需要更新"""