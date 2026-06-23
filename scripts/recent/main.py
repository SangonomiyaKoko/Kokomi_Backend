#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import gc
import time
import redis
import httpx
import pymysql
import asyncio
import traceback
from tqdm import tqdm
from redis import Redis
from httpx import AsyncClient
from pymysql import Connection
from typing import Any, Iterator

from logger import TqdmAwareLogger, get_formatted_date, logger
from exception import write_exception
from updater import UserStats, UserUpdater
from refresher import UserRecentUpdater
from syncer import UserStatsSyncer
from api import fetch_user_recent_data
from db_ops import get_recent_users, disable_user
from utils import get_current_timestamp
from settings import (
    REGION, 
    USE_TQDM,
    CLIENT_NAME, 
    SSL_CA_BUNDLE,
    REFRESH_INTERVAL, 
    MYSQL_CONFIG, 
    REDIS_CONFIG,
)



TIMEOUT = httpx.Timeout(connect=2.0, read=10.0, write=3.0, pool=2.0)

def progress_iterable(
    items: list[Any], desc: str, logger_obj: TqdmAwareLogger
) -> Iterator[Any]:
    """遍历列表，tqdm 模式下用进度条，否则日志输出进度。

    Args:
        items: 待遍历的列表。
        desc: 进度描述文本。
        logger_obj: TqdmAwareLogger 实例。

    Yields:
        列表中的每个元素。
    """
    if USE_TQDM:
        tqdm_desc = f'{get_formatted_date()} [INFO] {desc}'
        with tqdm(items, desc=tqdm_desc, total=len(items)) as pbar:
            for item in pbar:
                pbar.set_postfix_str(str(item))
                yield item
    else:
        total = len(items)
        for idx, item in enumerate(items, 1):
            logger_obj.info('%s - [%d/%d] | Current: %s', desc, idx, total, item)
            yield item

async def worker(mysql_connection: Connection, redis_client: Redis, async_client: AsyncClient):
    # 待更新用户列表
    # [user_id, level, limit, user_stats, stats_time], ...
    update_list = []
    # 待删除用户列表
    disable_list = []

    try:
        with mysql_connection.cursor() as cursor:
            rows = get_recent_users(cursor)
            for row in rows:
                if row[0] != 2023619512:
                    continue
                # 不可用用户直接退出
                if row[3] == 0:
                    disable_list.append(row[0])
                    continue

                # 用户level信息
                user_level=row[1]
                user_limit=row[2]

                # updated_at 为 NULL 说明该用户是新添加
                if row[10] is None:
                    update_list.append([row[0],user_level,user_limit,None,None])
                    continue
                
                # 读取用户在数据库中的最新stats数据
                user_stats = UserStats(
                    is_public=row[4],
                    total_battles=row[5],
                    pve_battles=row[6],
                    pvp_battles=row[7],
                    ranked_battles=row[8],
                    karma=row[9]
                )
                update_list.append([row[0],user_level,user_limit,user_stats,row[10]])
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Database operation exception: {error_name}")
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
    
    for account_id, user_level, user_limit, user_stats, update_time in update_list:
        try:
            # 只读取一次时间戳避免计算日期时出现不一致问题
            current_timestamp = get_current_timestamp()

            # 设置分布式锁防止出现并发写问题
            lock_key = f"refresh_lock:recent:{account_id}"
            lock_acquired = redis_client.set(lock_key, 1, nx=True, ex=60)
            if not lock_acquired:
                # 获取锁失败则直接跳过
                logger.info(f'{account_id} | Failed to acquire lock')
                continue

            # 检查用户数据是否需要更新
            # 对比mysql和sqlite数据库中用户的基本数据
            result = UserUpdater.main(
                account_id=account_id,
                user_limit=user_limit,
                current_timestamp=current_timestamp,
                user_latest_stats=user_stats,
                user_update_time=update_time
            )

            # # 对于没有变动的用户不需要更新
            # if not result:
            #     continue
            
            # 读取用户的最新数据
            responses = await fetch_user_recent_data(async_client, redis_client, account_id)
            if not responses:
                logger.info(f'{account_id} | Failed to obtain data')
                continue
                
            basic_data = responses[0]
            
            # 先刷新 MySQL 的用户基础信息
            try:
                update_timestamp = UserStatsSyncer.refresh(mysql_connection, account_id, basic_data)
            except Exception as e:
                error_name = type(e).__name__
                logger.error(f'{account_id} | Database operation error: {error_name}')
                write_exception(
                    error_type="DatabaseError",
                    error_name=error_name,
                    error_info=traceback.format_exc()
                )
                continue
            
            # 没有刷新时间说明刷新失败
            if update_timestamp is None:
                logger.error(f'{account_id} | Refresh failed')
                continue
                
            # 用户数据不存在
            basic_data = basic_data.get(str(account_id))
            if 'hidden_profile' not in basic_data and (
                basic_data is None or 
                'statistics' not in basic_data
            ):
                if account_id not in disable_list:
                    disable_list.append(account_id)
                logger.info(f'{account_id} | User not found')
                continue

            result = await UserRecentUpdater.main(
                account_id=account_id,
                user_level=user_level,
                responses=responses,
                current_timestamp=current_timestamp,
                update_timestamp=update_timestamp
            )
            logger.info(f'{account_id} | {result}')
        except Exception as e:
            error_name = type(e).__name__
            logger.error(f'{account_id} | Refresh failed: {error_name}')
            write_exception(
                error_type="DatabaseError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
        finally:
            # 删除分布式锁
            redis_client.delete(lock_key)

async def main():
    redis_client = None
    mysql_connection = None

    while True:
        start = time.monotonic()
        
        try:
            redis_client = redis.Redis(**REDIS_CONFIG)
            # 设置当前服务状态，用于外部监控系统判断服务是否正常运行
            redis_client.set(f'status:{CLIENT_NAME}', 1, ex=int(REFRESH_INTERVAL*1.5))
            mysql_connection = pymysql.connect(**MYSQL_CONFIG)
            if SSL_CA_BUNDLE:
                # 处理俄服接口证书效验问题
                async_client = httpx.AsyncClient(timeout=TIMEOUT, verify=SSL_CA_BUNDLE)
            else:
                async_client = httpx.AsyncClient(timeout=TIMEOUT)

            await worker(
                mysql_connection=mysql_connection,
                redis_client=redis_client,
                async_client=async_client
            )
        except Exception as e:
            # 记录错误信息
            error_name = type(e).__name__
            logger.error(f"A fatal error occurred in the loop: {error_name}")
            write_exception(
                error_type="ProgramError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )

            # 严重错误导致的循环中断，删除用于标记服务状态的key
            try:
                if redis_client:
                    redis_client.delete(f'status:{CLIENT_NAME}')
            except Exception as e:
                error_name = type(e).__name__
                logger.error(f'Failed to delete status key: {error_name}')
        finally:
            # 大部分情况下每次循环运行时间远小于刷新间隔，大部分时间都处于sleep状态
            # 为了减少相关资源占用，每次循环结束后关闭所有连接，释放资源空间
            # 等待下一次循环运行时再重新建立连接
            if async_client:
                await async_client.aclose()
            if redis_client:
                redis_client.close()
            if mysql_connection:
                mysql_connection.close()
            async_client = None
            redis_client = None
            mysql_connection = None
            gc.collect()

        # 计算本次循环的实际运行时间，并根据刷新间隔决定是否需要sleep
        elapsed = time.monotonic() - start
        logger.info('This loop took %.2f seconds', round(elapsed, 2))
        sleep_time = max(0, round(REFRESH_INTERVAL - elapsed, 2))

        if sleep_time >= 1:
            logger.info(f'The process sleeps for {sleep_time} seconds')
            time.sleep(sleep_time)
        else:
            logger.info(f'The process sleeps for 1 seconds')
            time.sleep(1)
        logger.info('-'*70)

def handler(*_):
    """信号处理器，退出"""
    logger.info('The process is closing')
    os._exit(0)

if __name__ == '__main__':
    logger.info('Start running service: %s', CLIENT_NAME)
    logger.info('Service refresh interval: %s seconds', REFRESH_INTERVAL)
    logger.info('Current node region: %s', REGION.upper())

    if os.name != 'nt':
        # 在非Windows系统上注册SIGTERM信号处理器，在接收到SIGTERM信号时关闭服务
        import signal
        signal.signal(signal.SIGTERM, handler)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # 在Windows系统上，无法捕获SIGTERM信号，但可以通过捕获KeyboardInterrupt异常来实现类似的功能
        handler()