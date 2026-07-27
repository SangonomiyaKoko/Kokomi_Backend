#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import gc
import time
import redis
import pymysql
import traceback
from tqdm import tqdm
from redis import Redis
from celery import Celery
from pymysql import Connection
from typing import Any, Iterator

from logger import TqdmAwareLogger, get_formatted_date, logger
from updater import RefreshPlanStats
from exception import write_exception
from db_ops import (
    get_max_id,
    read_table_batch,
    write_stats_to_db
)
from settings import (
    REGION, 
    USE_TQDM,
    CLIENT_NAME, 
    REFRESH_INTERVAL, 
    MYSQL_CONFIG, 
    REDIS_CONFIG,
    RABBITMQ_CONFIG,
    BATCH_SIZE
)


def send_task(celery_app: Celery, task_name: str, entity_id: int, queue: str) -> bool:
    """向指定队列发送 Celery 任务。

    Args:
        celery_app: Celery 应用实例。
        task_name: 任务名称。
        entity_id: 实体 ID（用户或公会 ID）。
        queue: 目标队列名。

    Returns:
        True 表示发送成功，False 表示失败。
    """
    try:
        celery_app.send_task(
            name=task_name, 
            args=[{'uid': entity_id}], 
            queue=queue
        )
        return True
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Send Task failed: {entity_id} | {error_name}")
        write_exception(
            error_type="CeleryError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
        return False
    
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
        # total = len(items)
        for idx, item in enumerate(items, 1):
            # logger_obj.info('%s - [%d/%d] | Current: %s', desc, idx, total, item)
            yield item

def worker(mysql_connection: Connection, redis_client: Redis, lock_client: Redis, celery_app: Celery) -> None:
    """单轮维护调度执行体

    用户刷新 ID 筛选与 Celery 任务分发

    Args:
        mysql_connection: MySQL 数据库连接
        redis_client: Redis 客户端
        celery_app: Celery 应用实例
    """
        
    # 更新玩家的基本数据
    refresh_plan = RefreshPlanStats()
    try:
        with mysql_connection.cursor() as cursor:
            # 读取自增 ID 列最大值作为终止值
            max_id = get_max_id(cursor)

            logger.enable_tqdm()
            for start_id in progress_iterable(
                items=range(1, max_id + 1, BATCH_SIZE),
                desc="Processing users",
                logger_obj=logger
            ):
                end_id = start_id + BATCH_SIZE - 1
                rows = read_table_batch(cursor, start_id, end_id)
                if not rows:
                    continue
                
                # 统计并获取本批到期 ID
                due_ids = refresh_plan.add_batch(rows)
                if len(due_ids) == 0:
                    continue

                # 通过 Redis 批量加锁
                try:
                    pipe = lock_client.pipeline()
                    keys = [f"refresh_lock:user:{uid}" for uid in due_ids]
                    for key in keys:
                        pipe.set(key, 1, nx=True, ex=4*3600)
                    results = pipe.execute()

                    locked_ids = [due_ids[i] for i, r in enumerate(results) if r]
                    refresh_plan.add_locked_ids(locked_ids)
                except Exception:
                    logger.warning('Failed to set the distributed lock')
            logger.disable_tqdm()

            # 平衡未来 24h 内的计划更新分布
            refresh_plan.rebalance_plan()
            
            # 将统计结果写入数据库
            write_stats_to_db(cursor, refresh_plan.get_db_update_data())

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

    skipped = refresh_plan.total_due - refresh_plan.locked
    logger.info(
        'User update schedule - Total: %s | Locked: %s | Skipped: %s',
        refresh_plan.total_due, refresh_plan.locked, skipped
    )
    logger.info('Planned user updates within today: %s', refresh_plan.today_remained_count)

    update_ids = refresh_plan.get_update_ids()
    len_update_ids = len(update_ids)
    logger.info(f'Current loop plan update count: {len_update_ids}')

    if len_update_ids != 0:
        failed_count = 0

        logger.enable_tqdm()
        for update_data in progress_iterable(
            items=update_ids, 
            desc=f"Processing user",
            logger_obj=logger
        ):
            result = send_task(celery_app, f'user_refresh', update_data, 'refresh_queue')
            if not result:
                redis_client.delete(f"refresh_lock:user:{update_data}")
                failed_count += 1
        logger.disable_tqdm()
        
        logger.info(f'Task sent completed - Success: {len_update_ids - failed_count} | Failed: {failed_count}')

def main():
    """主调度循环

    初始化 Celery 应用后进入无限循环：建立连接 → worker() 执行维护任务 →
    释放连接资源 → 按 REFRESH_INTERVAL 补齐 sleep。
    异常不会中断循环，但会清理服务状态 key 以便外部监控感知。
    """
    redis_client = None
    mysql_connection = None
    broker_url = f"pyamqp://{RABBITMQ_CONFIG['user']}:{RABBITMQ_CONFIG['password']}@{RABBITMQ_CONFIG['host']}/"
    celery_app = Celery(
        'producer',
        broker=broker_url,
        broker_connection_retry_on_startup=True
    )
    while True:
        start = time.monotonic()

        try:
            redis_client = redis.Redis(**REDIS_CONFIG)
            # 设置当前服务状态，用于外部监控系统判断服务是否正常运行
            redis_client.set(f'status:{CLIENT_NAME}', 1, ex=int(REFRESH_INTERVAL*1.5))
            LOCK_REDIS_CONFIG = REDIS_CONFIG.copy()
            LOCK_REDIS_CONFIG['db'] += 1
            lock_client = redis.Redis(**LOCK_REDIS_CONFIG)
            mysql_connection = pymysql.connect(**MYSQL_CONFIG)

            worker(
                mysql_connection=mysql_connection,
                redis_client=redis_client,
                lock_client=lock_client,
                celery_app=celery_app
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
        main()
    except KeyboardInterrupt:
        # 在Windows系统上，无法捕获SIGTERM信号，但可以通过捕获KeyboardInterrupt异常来实现类似的功能
        handler()