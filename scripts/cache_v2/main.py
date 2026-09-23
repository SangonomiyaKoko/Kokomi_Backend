#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gc
import os
import time
import psutil
import signal
import asyncio
import traceback

import redis
import httpx
import pymysql
from shard import RedisKeys, ServicesName

from .worker import run_worker
from .logger import logger, write_exception
from .settings import (
    REGION, 
    ENV_FILE,
    MEM_MONITOR,
    MYSQL_CONFIG,
    REDIS_CONFIG,
    SSL_CA_BUNDLE,
    REQUEST_TIMEOUT,
    REFRESH_INTERVAL
)


async def run_once() -> None:
    """执行一次完整更新循环并清理本轮资源"""
    mysql_conn = None
    redis_client = None
    async_client = None

    status_key = RedisKeys.services(ServicesName.CACHE_V2)

    try:
        # 初始化资源
        mysql_conn = pymysql.connect(**MYSQL_CONFIG)
        redis_client = redis.Redis(**REDIS_CONFIG)
        if SSL_CA_BUNDLE:
            # 处理俄服特殊的SSL证书
            async_client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT,
                verify=SSL_CA_BUNDLE
            )
        else:
            async_client = httpx.AsyncClient(
                timeout=REQUEST_TIMEOUT
            )

        # 设置当前服务状态，用于外部监控系统判断服务是否正常运行
        redis_client.set(
            name=status_key,
            value=1,
            ex=REFRESH_INTERVAL + 10
        )

        # 执行工作任务
        await run_worker(
            mysql_conn=mysql_conn,
            redis_client=redis_client,
            async_client=async_client
        )

    except Exception as e:
        error_name = type(e).__name__
        error_id = write_exception(
            error_type="ProgramError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
        logger.error(f"Fatal error: {error_name} - {error_id}")
        try:
            if redis_client:
                redis_client.delete(status_key)
        except Exception as e:
            logger.error(f'Failed to delete status key: {type(e).__name__}')
    finally:
        if mysql_conn:
            mysql_conn.close()
        if redis_client:
            redis_client.close()
        if async_client:
            await async_client.aclose()


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


async def main() -> None:
    """主函数，程序入口"""

    pid = os.getpid()
    logger.info('Service startup parameters:')
    logger.info('├─ Service:      %s', ServicesName.CACHE_V2)
    logger.info('├─ Node region:  %s', REGION.upper())
    logger.info('├─ Env file:     %s', ENV_FILE)
    logger.info('├─ Refresh:      %s s', REFRESH_INTERVAL)
    logger.info('├─ Platform:     %s', os.name)
    logger.info('└─ Process ID:   %s', pid)

    # 启动调度器
    await start_scheduler(pid)

def _handler(*_):
    """信号处理器，退出"""
    logger.info('The process is closing')
    os._exit(0)

if __name__ == '__main__':
    if os.name != 'nt':
        signal.signal(signal.SIGTERM, _handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        _handler()