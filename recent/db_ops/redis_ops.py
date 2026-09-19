from typing import Iterator
from contextlib import contextmanager

from redis import Redis


@contextmanager
def refresh_lock(
    lock_key: str, redis_client: Redis
) -> Iterator[bool]:
    """分布式锁，防止并发重复刷新同一用户"""
    if not lock_key:
        yield False
        return

    # 任务理论上不存在超过 20s 的可能
    # 因此设置 60s 过期时间防止死锁
    acquired = redis_client.set(
        name=lock_key, 
        value=1, 
        nx=True, 
        ex=60
    )

    if not acquired:
        # 未成功获取到锁，不再次进行尝试
        yield False
        return
    
    try:
        yield True
    finally:
        # 释放锁
        redis_client.delete(lock_key)