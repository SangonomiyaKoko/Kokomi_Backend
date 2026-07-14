#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import gc
import time
import redis
import msgpack
import pymysql
import requests
import traceback
from tqdm import tqdm
from redis import Redis
from requests import Session
from pymysql import Connection
from typing import Any, Iterator

from logger import TqdmAwareLogger, logger
from updater import UserCacheUpdater
from exception import write_exception
from utils import get_formatted_date, get_current_timestamp
from db_ops import (
    get_update_ids,
    read_ship_data,
    read_ship_record,
    read_game_version,
    update_ship_record,
    get_ship_leaderboard,
    read_enabled_ship_ids
)
from settings import (
    REGION, 
    USE_TQDM,
    CLIENT_NAME, 
    SSL_CA_BUNDLE,
    REFRESH_INTERVAL,
    MYSQL_CONFIG, 
    REDIS_CONFIG,
    DATA_DIR
)


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

def worker(mysql_connection: Connection, redis_client: Redis, session: Session) -> None:
    """单轮缓存更新执行体

    加载待更新用户列表和船只基准数据,对每个用户调用 UserCacheUpdater.main() 完成数据拉取与写入。

    Args:
        mysql_connection: MySQL 数据库连接
        redis_client: Redis 客户端
    """

    # 加载待更新用户列表、船只基准数据和极值记录
    try:
        with mysql_connection.cursor() as cursor:
            # 读取需要更新的用户id列表
            update_ids = get_update_ids(cursor)

            len_update_ids = len(update_ids)
            logger.info(f'Current loop plan update count: {len_update_ids}')

            # 不可用船只id列表
            enabled_ship_ids = read_enabled_ship_ids(cursor)

            # 加载符合排行榜统计船只的数据
            ship_data = read_ship_data(cursor)

            # 读取船只相关字段的最高记录信息
            ship_record = read_ship_record(cursor)

            # 读取最新版本信息
            game_version, version_start = read_game_version(cursor)
        
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Database operation exception: {error_name}")
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
        return
    
    if len_update_ids > 0:
        # 主更新循环
        updater = UserCacheUpdater(enabled_ship_ids, ship_record, ship_data, game_version, version_start)
        logger.enable_tqdm()
        for update_data in progress_iterable(
            items=update_ids, 
            desc="Processing cache",
            logger_obj=logger
        ):
            updater.main(
                mysql_connection,
                redis_client,
                session,
                update_data
            )
        logger.disable_tqdm()

        try:
            with mysql_connection.cursor() as cursor:
                row_count = update_ship_record(cursor, updater.ship_record)
                logger.info(f"Highest record of ships refreshed: {row_count}")
                
            mysql_connection.commit()
        except Exception as e:
            mysql_connection.rollback()
            error_name = type(e).__name__
            logger.error(f"Database operation exception: {error_name}")
            write_exception(
                error_type="DatabaseError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
    
    total_top50_users = 0
    payload = {
        'time': get_current_timestamp(),
        'data': {}
    }
    try:
        with mysql_connection.cursor() as cursor:
            for ship_id, ship_stats in ship_data.items():
                if ship_stats[1] is None:
                    continue
                min_battles = ship_stats[0]
                ship_ranking_key = f"leaderboard:ship:{ship_id}"
                start = 0
                stop = 49
                total_users = redis_client.zcard(ship_ranking_key)
                if total_users == 0:
                    continue

                total_top50_users += total_users

                users = redis_client.zrevrange(ship_ranking_key, start, stop)
                if len(users) == 0:
                    continue

                ship_ranking = {
                    'limit': min_battles,
                    'users': total_users,
                    'rows': get_ship_leaderboard(cursor, ship_id, users)
                }

                payload['data'][ship_id] = ship_ranking

    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Database operation exception: {error_name}")
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
    
    logger.info(f'Cached top50 users: {total_top50_users}')
    
    packed_bytes = msgpack.packb(payload, use_bin_type=True)
    with open(DATA_DIR / 'trash/ship_ranking.msgpack', "wb") as f:
        f.write(packed_bytes)


def main():
    """主调度循环

    无限循环执行：建立连接 → worker() 更新缓存 → 写入完成时间戳 →
    释放连接资源 → 按 REFRESH_INTERVAL 补齐 sleep。
    异常不会中断循环，但会清理服务状态 key 以便外部监控感知。
    """
    redis_client = None
    mysql_connection = None
    session = None

    while True:
        start = time.monotonic()
        
        try:
            redis_client = redis.Redis(**REDIS_CONFIG)
            # 设置当前服务状态，用于外部监控系统判断服务是否正常运行
            redis_client.set(f'status:{CLIENT_NAME}', 1, ex=int(REFRESH_INTERVAL*1.5))
            mysql_connection = pymysql.connect(**MYSQL_CONFIG)
            session = requests.Session()
            if SSL_CA_BUNDLE:
                # 处理俄服接口证书效验问题
                session.verify= SSL_CA_BUNDLE

            worker(
                mysql_connection=mysql_connection,
                redis_client=redis_client,
                session = session
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
            if redis_client:
                redis_client.close()
            if mysql_connection:
                mysql_connection.close()
            if session:
                session.close()
            redis_client = None
            mysql_connection = None
            session = None

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
        main()
    except KeyboardInterrupt:
        # 在Windows系统上，无法捕获SIGTERM信号，但可以通过捕获KeyboardInterrupt异常来实现类似的功能
        handler()