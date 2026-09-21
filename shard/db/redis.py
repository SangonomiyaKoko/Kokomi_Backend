from typing import Iterator
from contextlib import contextmanager

from redis import Redis


@contextmanager
def distributed_lock(
    lock_key: str, redis_client: Redis, ex: int = 60
) -> Iterator[bool]:
    """分布式锁，防止并发重复刷新，默认 60s 过期

    未获取到锁时 yield False，调用方据此跳过本轮，不重试
    """
    if not lock_key:
        yield False
        return

    acquired = redis_client.set(
        name=lock_key,
        value=1,
        nx=True,
        ex=ex
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
