import traceback
from typing import Iterator
from contextlib import contextmanager

from redis import Redis
from requests import Session
from pymysql import Connection

from shard import RedisKeys, progress_iterable

from .logger import logger, write_exception
from .syncer import ClanUsersSyncer
from .requester import APIRequester
from .updater import (
    RefreshPlanStats,
    DueClanContainer
)
from .db_ops import (
    mysql_read_only,
    mysql_transaction,
    MySQLRepository
)
from .settings import (
    BATCH_SIZE,
    MAX_DISPATCH_PER_ROUND
)


@contextmanager
def refresh_lock(
    lock_key: str, redis_client: Redis
) -> Iterator[bool]:
    """分布式锁，防止并发重复刷新同一用户"""
    if not lock_key:
        yield False
        return

    # 任务理论上不存在超过 20s 的可能
    # 因此设置 60s 过期时间防止死锁
    acquired = redis_client.set(
        name=lock_key, 
        value=1, 
        nx=True, 
        ex=60
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

async def run_worker(
    mysql_conn: Connection,
    redis_client: Redis,
    session: Session
) -> None:
    """单轮公会更新调度执行体"""

    # 扫描全表，筛选出本轮需要更新的公会
    refresh_plan = RefreshPlanStats()
    candidates = DueClanContainer(capacity=MAX_DISPATCH_PER_ROUND)

    with mysql_read_only(mysql_conn) as cursor:
        # 读取自增 ID 列最大值作为终止值
        max_id = MySQLRepository.load_max_id(cursor)

        if max_id == 0:
            logger.info("No local clans")
            return

        logger.enable_tqdm()
        try:
            for start_id in progress_iterable(
                items=range(1, max_id + 1, BATCH_SIZE),
                entry='batch',
                logger=logger
            ):
                rows = MySQLRepository.load_table_batch(
                    cursor=cursor,
                    start_id=start_id,
                    end_id=start_id + BATCH_SIZE - 1
                )
                if not rows:
                    continue

                # 统计并获取本批到期公会，交由容器按优先级保留最紧急的一批
                due_clans = refresh_plan.add_batch(rows)
                if not due_clans:
                    continue

                candidates.offer(due_clans)
        finally:
            logger.disable_tqdm()

    # 平衡未来 24h 内的计划更新分布，并将统计结果写入数据库
    refresh_plan.rebalance_plan()
    with mysql_transaction(mysql_conn) as cursor:
        MySQLRepository.write_stats(
            cursor=cursor,
            stats_data=refresh_plan.get_db_update_data()
        )

    update_ids = candidates.get_clan_ids()
    if len(update_ids) == 0:
        logger.info("No pending tasks")
        return

    new_count = 0

    logger.enable_tqdm()
    try:
        for clan_id in progress_iterable(
            items=update_ids,
            entry='clan',
            logger=logger
        ):
            # 获取工会内用户数据
            response = APIRequester.fetch(
                redis_client=redis_client, 
                session=session, 
                clan_id=clan_id
            )
            if not isinstance(response, list):
                logger.info(f'{clan_id} | Failed to obtain data')
                continue

            users = {}
            for user_info in response:
                users[user_info['id']] = user_info['name']

            with mysql_read_only(mysql_conn, clan_id) as cursor:
                local_data = MySQLRepository.get_existing_members(cursor, clan_id)
                existing_ids = MySQLRepository.get_existing_users(cursor, list(users.keys()))

            missing_ids = [uid for uid in users.keys() if uid not in existing_ids]
            if missing_ids:
                insert_lock_key = RedisKeys.insert_lock()
                with refresh_lock(insert_lock_key, redis_client) as locked:
                    if not locked:
                        logger.info(f'{clan_id} | FAILED - AcquireLockFailed')
                        continue
                    
                    with mysql_transaction(mysql_conn, clan_id) as cursor:
                        MySQLRepository.init_new_users(cursor, missing_ids, users)
                    new_count += len(missing_ids)

            ClanUsersSyncer.refresh(
                conn=mysql_conn, 
                clan_id=clan_id, 
                users=users,
                old_data=local_data
            )
    finally:
        logger.disable_tqdm()

    # 到期总数与本轮处理数之差即积压量：受容器容量限制而本轮未能排上的公会
    logger.info(
        'Clan update schedule - Due: %s | Consumed: %s | Waiting: %s',
        refresh_plan.total_due,
        len(update_ids),
        refresh_plan.total_due - len(update_ids)
    )
    logger.info(
        'Planned clan updates within today: %s',
        refresh_plan.today_remained_count
    )
    if new_count:
        logger.info('New users inserted this loop: %s', new_count)
