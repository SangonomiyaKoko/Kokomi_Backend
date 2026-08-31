import gc
import time
import asyncio
import traceback

import httpx
import pymysql
import redis

from loggers import logger, write_exception
from worker import run_worker
from context import RunContext
from utils import TimeUtils
from settings import (
    TIMEOUT,
    CLIENT_NAME,
    SSL_CA_BUNDLE,
    REFRESH_INTERVAL,
    MYSQL_CONFIG,
    REDIS_CONFIG
)


def create_resources(run_ctx: RunContext) -> None:
    """创建所有需要的资源连接"""
    run_ctx.redis_client = redis.Redis(**REDIS_CONFIG)
    run_ctx.mysql_connection = pymysql.connect(**MYSQL_CONFIG)

    if SSL_CA_BUNDLE:
        run_ctx.async_client = httpx.AsyncClient(
            timeout=TIMEOUT,
            verify=SSL_CA_BUNDLE
        )
    else:
        run_ctx.async_client = httpx.AsyncClient(
            timeout=TIMEOUT
        )


async def cleanup_resources(run_ctx: RunContext) -> None:
    """清理资源连接"""
    async_client = getattr(run_ctx, 'async_client', None)
    redis_client = getattr(run_ctx, 'redis_client', None)
    mysql_connection = getattr(run_ctx, 'mysql_connection', None)

    if async_client:
        await async_client.aclose()
    if redis_client:
        redis_client.close()
    if mysql_connection:
        mysql_connection.close()

    gc.collect()


async def run_once() -> None:
    """执行一次完整更新循环并清理本轮资源"""
    run_ctx = RunContext()
    try:
        create_resources(run_ctx)

        # 设置当前服务状态
        run_ctx.redis_client.set(
            name=f'status:{CLIENT_NAME}',
            value=1,
            ex=int(REFRESH_INTERVAL * 1.5),
        )

        # 执行工作任务
        await run_worker(run_ctx)

    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"A fatal error occurred in the loop: {error_name}")
        write_exception(
            error_type="ProgramError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
    finally:
        try:
            if getattr(run_ctx, 'redis_client', None):
                run_ctx.redis_client.delete(f'status:{CLIENT_NAME}')
        except Exception as e:
            logger.error(f'Failed to delete status key: {type(e).__name__}')

        await cleanup_resources(run_ctx)


async def start_scheduler() -> None:
    """主调度器"""
    while True:
        start = time.monotonic()

        await run_once()

        elapsed = time.monotonic() - start
        logger.info('This loop took %.2f seconds', round(elapsed, 2))
        sleep_time = max(0, round(REFRESH_INTERVAL - elapsed, 2))

        if sleep_time >= 1:
            logger.info(f'The process sleeps for {sleep_time} seconds')
            await asyncio.sleep(sleep_time)
        else:
            logger.info(f'The process sleeps for 1 seconds')
            await asyncio.sleep(1)
        logger.info('-'*70)
