#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import gc
import time
import redis
import httpx
import pymysql
import asyncio
import traceback
from redis import Redis
from httpx import AsyncClient
from pymysql import Connection
from typing import Optional, Tuple

from loggers import logger, write_exception
from worker import run_worker
from settings import (
    CLIENT_NAME, 
    SSL_CA_BUNDLE,
    REFRESH_INTERVAL, 
    MYSQL_CONFIG, 
    REDIS_CONFIG,
)


TIMEOUT = httpx.Timeout(connect=2.0, read=10.0, write=3.0, pool=2.0)


async def create_resources() -> Tuple[Redis, Connection, AsyncClient]:
    """创建所有需要的资源连接"""
    redis_client = redis.Redis(**REDIS_CONFIG)
    mysql_connection = pymysql.connect(**MYSQL_CONFIG)
    
    if SSL_CA_BUNDLE:
        async_client = httpx.AsyncClient(timeout=TIMEOUT, verify=SSL_CA_BUNDLE)
    else:
        async_client = httpx.AsyncClient(timeout=TIMEOUT)
    
    return redis_client, mysql_connection, async_client


async def cleanup_resources(
    redis_client: Optional[Redis],
    mysql_connection: Optional[Connection],
    async_client: Optional[AsyncClient]
) -> None:
    """清理资源连接"""
    if async_client:
        await async_client.aclose()
    if redis_client:
        redis_client.close()
    if mysql_connection:
        mysql_connection.close()
    
    gc.collect()


async def run_once() -> None:
    redis_client = None
    mysql_connection = None
    async_client = None

    try:
        redis_client, mysql_connection, async_client = await create_resources()
        
        # 设置当前服务状态
        redis_client.set(f'status:{CLIENT_NAME}', 1, ex=int(REFRESH_INTERVAL*1.5))
        
        # 执行工作任务
        await run_worker(
            mysql_connection=mysql_connection,
            redis_client=redis_client,
            async_client=async_client
        )
        
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
            if redis_client:
                redis_client.delete(f'status:{CLIENT_NAME}')
        except Exception as delete_error:
            error_name = type(delete_error).__name__
            logger.error(f'Failed to delete status key: {error_name}')
            
        await cleanup_resources(redis_client, mysql_connection, async_client)


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