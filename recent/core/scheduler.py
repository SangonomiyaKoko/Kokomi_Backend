import gc
import time
import psutil
import asyncio
import traceback

import httpx
import pymysql
import redis
from shard import ServicesName

from ..logger import logger, write_exception
from ..settings import (
    MEM_MONITOR,
    SSL_CA_BUNDLE,
    REQUEST_TIMEOUT,
    REFRESH_INTERVAL,
    MYSQL_CONFIG,
    REDIS_CONFIG
)

from .context import RunContext


def create_resources(run_ctx: RunContext) -> None:
    """创建所有需要的资源连接"""

    # 初始化中间件连接资源
    run_ctx.redis_client = redis.Redis(**REDIS_CONFIG)
    run_ctx.mysql_connection = pymysql.connect(**MYSQL_CONFIG)

    if SSL_CA_BUNDLE:
        # 处理俄服特殊的SSL证书
        run_ctx.async_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT,
            verify=SSL_CA_BUNDLE
        )
    else:
        run_ctx.async_client = httpx.AsyncClient(
            timeout=REQUEST_TIMEOUT
        )

    # 设置当前服务状态
    run_ctx.set_status_key()


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


async def run_once() -> None:
    """执行一次完整更新循环并清理本轮资源"""
    from .worker import run_worker
    
    run_ctx = RunContext()
    try:
        # 初始化资源
        create_resources(run_ctx)

        # 执行工作任务
        await run_worker(run_ctx)

        # 检查本次任务的失败率，超过 10% 的阈值则触发告警
        # 此处只有程序异常抛出的异常会被计入，网络异常不会计入
        if run_ctx.failure_rate > 10:
            # TODO: 用于对接后续的告警系统
            logger.warning(f'Task failure rate exceeded: {run_ctx.failure_rate}')

        logger.info(f'Summary: {run_ctx.run_counter.metrics}')

    except Exception as e:
        error_name = type(e).__name__
        error_id = write_exception(
            error_type="ProgramError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
        logger.error(f"Fatal error: {error_name} - {error_id}")
        try:
            if getattr(run_ctx, 'redis_client', None):
                run_ctx.del_status_key()
        except Exception as e:
            logger.error(f'Failed to delete status key: {type(e).__name__}')
    finally:
        await cleanup_resources(run_ctx)


async def start_scheduler(pid: int) -> None:
    """主调度器"""
    process = None
    # MEM_MONITOR 模式下监控内存占用趋势
    if MEM_MONITOR:
        process = psutil.Process(pid)

    while True:
        start = time.monotonic()

        await run_once()

        gc.collect()

        if process:
            logger.info(
                'Memory usage: %.2f MB',
                process.memory_info().rss / 1024 / 1024,
            )

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
