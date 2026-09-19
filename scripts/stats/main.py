#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import gc
import time
import redis
import pymysql
import requests
import traceback
from redis import Redis
from requests import Session
from pymysql import Connection
from pathlib import Path

from shard import (
    RedisKeys,
    ServicesName,
    progress_iterable
)

from .logger import logger, write_exception
from .analytics import ShipStatsAggregator
from .api import fetch_latest_version
from .db_ops import (
    get_max_id,
    get_version,
    read_ship_ids,
    read_ship_data,
    refresh_version,
    refersh_tracking_time,
    refresh_database_meta,
    archive_base_table,
    anaylyze_mysql_tables
)
from .recent import (
    ShipRecentAggregator,
    get_agg_rows,
    read_recent_data,
    verify_ship_exist,
    cleanup_done_rows,
    aggregate_recent,
    update_status,
    insert_error
)
from .updater import (
    get_pvp_cache,
    refresh_table_meta,
    update_ship_pvp_stats,
    update_users_stats_table,
    update_battles_stats_table,
    update_rating_distribution_table
)
from .settings import (
    REGION,
    SSL_CA_BUNDLE,
    REFRESH_INTERVAL,
    MYSQL_CONFIG,
    REDIS_CONFIG,
    BATCH_SIZE,
    SQLITE_DIR
)


def worker(mysql_connection: Connection, redis_client: Redis, session: Session) -> None:
    """执行统计聚合和排行榜刷新

    Args:
        mysql_connection: MySQL 数据库连接对象
    """
    game_version = None

    # 更新游戏版本和归档基本数据
    try:
        with mysql_connection.cursor() as cursor:
            # 读取本地数据中的最新赛季
            game_version = get_version(cursor)
            ship_ids = read_ship_ids(cursor)
            ship_data = read_ship_data(cursor)

            # 请求 API 获取最新版本信息
            latest_version = fetch_latest_version(session, redis_client)

            if not isinstance(latest_version, dict):
                # 请求 API 失败
                logger.info('Failed to obtain latest version')
            elif game_version:
                # 本地有缓存数据
                refresh_version(cursor, game_version, latest_version)
                game_version = latest_version.get('short')
            else:
                # 无本地缓存数据
                refresh_version(cursor, None, latest_version)
                game_version = latest_version.get('short')

            # 归档基本信息表
            archive_base_table(cursor)
            
            # 刷新统计时间
            refersh_tracking_time(cursor, 'base_table', 'archive_time')

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

    # 没有船只信息或者版本信息
    if len(ship_ids) == 0 or game_version is None:
        return
    
    # 处理暂存的船只近期数据
    recent_aggregator = ShipRecentAggregator(ship_ids)
    try:
        processed = 0
        deleted = 0

        with mysql_connection.cursor() as cursor:
            # 检查存档表的完整性
            verify_ship_exist(cursor, game_version, ship_ids)
            
            # 清理已处理数据
            deleted = cleanup_done_rows(cursor)

            # 获取数据范围
            agg_rows = get_agg_rows(cursor)
            if agg_rows > 0:
                # 计算总批次数
                total_batches = (agg_rows + BATCH_SIZE - 1) // BATCH_SIZE
                
                last_uuid = None
                # 分批次读取用户缓存数据
                logger.enable_tqdm()
                for _ in progress_iterable(
                    items=range(total_batches),
                    entry='cache',
                    logger=logger
                ):
                    # 从数据库获取一批原始缓存数据
                    rows = read_recent_data(cursor, last_uuid, BATCH_SIZE)
                    # 将这批数据添加到聚合器
                    recent_aggregator.add_batch(rows)
                    # 更新游标：本批次最后一条的 uuid
                    if rows:
                        last_uuid = rows[-1][0]
                        processed += len(rows)
                logger.disable_tqdm()

                # 将数据写入数据库
                aggregate_recent(cursor, recent_aggregator.get_ship_aggregator())
                update_status(cursor, recent_aggregator.get_status_params())
                insert_error(cursor, recent_aggregator.get_error_params())
        
        logger.info(
            'Recent data aggregated - Processed: %s | Deleted: %s',
            processed, deleted
        )
        
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

    # 从 MySQL 读取原始数据并聚合计算
    try:
        with mysql_connection.cursor() as cursor:
            # 获取数据范围
            max_id = get_max_id(cursor)
            if max_id == 0:
                return

            # 初始化聚合器
            aggregator = ShipStatsAggregator(ship_data)

            # 分批次读取用户缓存数据
            logger.enable_tqdm()
            for batch_offset in progress_iterable(
                items=range(0, max_id, BATCH_SIZE),
                entry='cache',
                logger=logger
            ):
                # 从数据库获取一批原始缓存数据
                rows = get_pvp_cache(cursor, batch_offset, BATCH_SIZE)
                # 将这批数据添加到聚合器
                aggregator.add_batch(rows)
            logger.disable_tqdm() 

            mysql_tables,mysql_rows,mysql_sizes = anaylyze_mysql_tables(cursor)
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Database operation exception: {error_name}")
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
        return 

    db_files = list(SQLITE_DIR.rglob("*.db"))
    file_count = len(db_files)
    total_size_kb = 0

    file_names = [f.name for f in db_files]
    if file_count > 0:
        # 分批次读取用户缓存数据
        logger.enable_tqdm()
        for file in progress_iterable(
            items=file_names,
            entry='file',
            logger=logger
        ):
            try:
                file_path = Path(SQLITE_DIR / file)
                total_size_kb += file_path.stat().st_size // 1024
            except Exception:
                continue
        logger.disable_tqdm() 

    if file_count == 0:
        avg_size_kb = 0
    else:
        avg_size_kb = total_size_kb // file_count
    if total_size_kb // 1024 // 1024 != 0:
        total_size_gb = round(total_size_kb / 1024 / 1024, 2)
    else:
        total_size_gb = '< 1'

    logger.info(
        'Recent file summary - Files: %s | Size: %s GB | Avg: %s KB',
        file_count, total_size_gb, avg_size_kb
    )
    
    if mysql_sizes // 1024 // 1024 != 0:
        mysql_size_gb = round(mysql_sizes / 1024 / 1024, 2)
    else:
        mysql_size_gb = '< 1'
    logger.info(
        'MySQL table summary - Tables: %s | Rows: %s | Size: %s GB',
        mysql_tables, mysql_rows, mysql_size_gb
    )

    # 更新 MySQL 统计表
    try:
        with mysql_connection.cursor() as cursor:
            # 更新服务器场次平均统计表
            update_battles_stats_table(cursor, aggregator.compute_battle_averages(ship_ids))

            # 更新服务器用户平均统计表
            update_users_stats_table(cursor, aggregator.compute_user_averages(ship_ids))

            # 更新 Rating 分布统计表
            update_rating_distribution_table(cursor, aggregator.compute_rating_percentiles())

            # 更新船只持有统计数据
            update_ship_pvp_stats(cursor, aggregator.compute_ownership_stats(ship_ids))

            # 更新表的统计信息
            refresh_table_meta(cursor, aggregator.aggregation_stats())

            # 更新 SQLite 统计信息
            refresh_database_meta(cursor, 'sqlite_files', file_count)
            refresh_database_meta(cursor, 'sqlite_size_kb', total_size_kb )

            # 更新 MySQL 统计信息
            refresh_database_meta(cursor, 'mysql_tables', mysql_tables)
            refresh_database_meta(cursor, 'mysql_rows', mysql_rows)
            refresh_database_meta(cursor, 'mysql_size_kb', mysql_sizes)

            # 记录更新时间
            refersh_tracking_time(cursor, 'ship_stats', 'update_time')

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

def main():
    """主服务入口，按配置的刷新间隔（REFRESH_INTERVAL）周期执行统计任务"""
    redis_client = None
    mysql_connection = None
    session = None

    status_key = RedisKeys.services(ServicesName.STATS)

    while True:
        start = time.monotonic()

        try:
            redis_client = redis.Redis(**REDIS_CONFIG)
            # 设置当前服务状态，用于外部监控系统判断服务是否正常运行
            redis_client.set(status_key, 1, ex=int(REFRESH_INTERVAL*1.5))
            mysql_connection = pymysql.connect(**MYSQL_CONFIG)
            session = requests.Session()
            if SSL_CA_BUNDLE:
                # 处理俄服接口证书效验问题
                session.verify= SSL_CA_BUNDLE
            
            # 执行核心统计任务
            worker(
                mysql_connection=mysql_connection,
                redis_client=redis_client,
                session=session
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
                    redis_client.delete(status_key)
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
        logger.info(f'This loop took {round(elapsed,2)} seconds')
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
    logger.info('Start running service: %s', ServicesName.STATS)
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