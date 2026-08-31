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

from logger import TqdmAwareLogger, get_formatted_date, logger
from api import fetch_clan_leagues
from exception import write_exception
from updater import update_clan_season
from db_ops import (
    need_update,
    get_update_ids,
    get_clan_leaderboard
)
from sqlite_ops import ensure_clan_battle_table
from utils import (
    is_cb_active,
    read_season_data,
    refresh_season_data,
    get_current_timestamp
)
from settings import (
    REGION, 
    USE_TQDM,
    CLIENT_NAME, 
    SSL_CA_BUNDLE,
    REFRESH_INTERVAL,
    MYSQL_CONFIG, 
    REDIS_CONFIG, 
    CLAN_REALM_MAP, 
    CLAN_LEAGUE_LIST,
    DATA_DIR
)


EXPECTED_LEAGUE_COUNT = 13  # 共13个联赛分段

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
    """单轮公会赛季数据刷新执行体

    读取赛季配置，确保赛季战表存在后，从 API 拉取全部 13 个联赛分段的公会列表，
    全量刷新 league 字段，对比筛选需更新的公会后逐条拉取详情写入 MySQL

    Args:
        mysql_connection: MySQL 数据库连接
        redis_client: Redis 客户端
    """
    # 读取当前赛季信息
    season_data = read_season_data()
    season_id = season_data.get('id', 0)
    if season_id == 0:
        logger.warning('Season_ID not configured')
        return
    logger.info(f"Current Season ID: {season_id}")
    
    # 最低每天刷新一次
    if not (
        need_update(mysql_connection, 'clan_season', 'refresh_time') or 
        is_cb_active(season_data['start'], season_data['finish'])
    ):
        logger.info(f'Update time not yet reached')
        return
    
    total_list = []
    league_count = {'0': 0, '1': 0, '2': 0, '3': 0, '4': 0}

    # 读取13个分段中所有工会的数据
    logger.enable_tqdm()
    for update_data in progress_iterable(
        items=CLAN_LEAGUE_LIST, 
        desc=f"Processing Leagues",
        logger_obj=logger
    ):
        league, division = update_data.split('-')
        league_data = fetch_clan_leagues(
            session = session,
            redis_client=redis_client,
            realm=CLAN_REALM_MAP.get(REGION),
            league=league,
            division=division
        )
        if league_data is None:
            logger.info(f'{update_data} | Failed to obtain data')
            continue
        
        if league_data == []:
            continue 

        latest_season_id = league_data[0][4]
        # 赛季变化处理
        if latest_season_id != season_id:
            if total_list != []:
                logger.warning(f'Clan battle season changed: {season_id} -> {latest_season_id}')
                return
            
            # 首次遇到新赛季，更新season_id
            logger.info(f'Clan battle season changed: {season_id} -> {latest_season_id}')
            season_id = latest_season_id
            refresh_season_data(season_id)
            redis_client.delete('leaderboard:clan')

        league_count[league] += len(league_data)
        total_list.extend(league_data)
    logger.disable_tqdm()

    logger.info(
        'Current active clans: 0(%d), 1(%d), 2(%d), 3(%d), 4(%d)', 
        league_count["0"], league_count["1"], league_count["2"], league_count["3"], league_count["4"]
    )

    if total_list == []:
        return
    
    # 确保当前赛季的工会战数据表（SQLite 数据库文件）存在
    table_status = ensure_clan_battle_table(season_id)
    if table_status is None:
        logger.warning(f'Failed to ensure SQLite database for season {season_id}')
        return

    if table_status:
        logger.info(f'New SQLite database for season {season_id} has been successfully created.')
    else:
        logger.debug(f'SQLite database for season {season_id} already exists')

    # 比较最新数据和数据库数据，确定需要更新的工会ID列表
    try:
        with mysql_connection.cursor() as cursor:
            update_ids = get_update_ids(cursor, season_id, total_list)
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
        return 
        
    len_update_ids = len(update_ids)
    if len_update_ids > 0:
        # 更新需要更新的工会数据
        logger.info(f'Clans update numbers: {len_update_ids}')
        logger.enable_tqdm()
        for update_data in progress_iterable(
            items=update_ids, 
            desc=f"Processing Clan",
            logger_obj=logger
        ):
            update_clan_season(session, redis_client, mysql_connection, season_id, update_data)
        logger.disable_tqdm()

    payload = {
        'time': get_current_timestamp(),
        'season': season_id,
        'clans': 0,
        'data': []
    }
    try:
        with mysql_connection.cursor() as cursor:
            clan_ranking_key = "leaderboard:clan"
            total_clans = redis_client.zcard(clan_ranking_key)
            if total_clans == 0:
                return
            
            payload['clans'] = total_clans

            clans = redis_client.zrevrange(clan_ranking_key, 0, 49)
            if len(clans) == 0:
                return

            payload['data'] = get_clan_leaderboard(cursor, clans)
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Database operation exception: {error_name}")
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )

    packed_bytes = msgpack.packb(payload, use_bin_type=True)
    with open(DATA_DIR / 'trash/clan_ranking.msgpack', "wb") as f:
        f.write(packed_bytes)

def main():
    """主调度循环

    无限循环执行：建立连接 → worker() 更新公会赛季数据 →
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