from redis import Redis
from requests import Session
from pymysql import Connection
from shard import (
    MySQLOPS,
    RefreshPlanStats,
    DueEntityContainer,
    progress_iterable
)

from .logger import logger
from .refresher import ClanUsersRefresher
from .db_ops import BasicDataRepository
from .settings import (
    BATCH_SIZE,
    REBALANCE_ENABLED,
    MAX_DISPATCH_PER_ROUND,
    REFRESH_ADVANCE_SECONDS,
    NEVER_REFRESHED_PRIORITY
)


async def run_worker(
    mysql_conn: Connection,
    redis_client: Redis,
    session: Session
) -> None:
    """单轮公会更新调度执行体"""

    candidates = DueEntityContainer(
        capacity=MAX_DISPATCH_PER_ROUND
    )
    refresh_plan = RefreshPlanStats(
        advance_seconds=REFRESH_ADVANCE_SECONDS,
        never_refreshed_priority=NEVER_REFRESHED_PRIORITY,
        distribution_len=4
    )

    with MySQLOPS.read_only(mysql_conn) as cursor:
        # 读取自增 ID 列最大值作为终止值
        max_id = BasicDataRepository.load_max_id(cursor)

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
                rows = BasicDataRepository.load_table_batch(
                    cursor=cursor,
                    start_id=start_id,
                    end_id=start_id + BATCH_SIZE - 1
                )
                if not rows:
                    continue

                # 统计并获取本批到期 ID
                due_clans = refresh_plan.add_batch(rows)
                if not due_clans:
                    continue

                candidates.offer(due_clans)
        finally:
            logger.disable_tqdm()
            
    logger.info(
        'Planned clan updates within today: %s',
        refresh_plan.today_remained_counts
    )

    # 平衡未来 24h 内的计划更新分布，并将统计结果写入数据库
    logger.debug(f"PreStats - {refresh_plan.bucket_counts}")
    if REBALANCE_ENABLED:
        refresh_plan.rebalance_plan()
        logger.debug(f"PostStats - {refresh_plan.bucket_counts}")
        logger.debug(f"Rebalanced: {refresh_plan.migrations}")

    update_ids = candidates.get_entity_ids()
    refresh_plan.counter.add_pending(len(update_ids))
    with MySQLOPS.transaction(mysql_conn) as cursor:
        BasicDataRepository.write_stats(
            cursor=cursor,
            stats_data=refresh_plan.to_db_data()
        )

    if len(update_ids) == 0:
        logger.info("No pending clans")
        return

    changed_actions = 0
    inserted_users = 0

    logger.enable_tqdm()
    try:
        for clan_id in progress_iterable(
            items=update_ids,
            entry='clan',
            logger=logger
        ):
            result = ClanUsersRefresher.refresh(
                mysql_conn=mysql_conn,
                redis_client=redis_client,
                session=session,
                clan_id=clan_id
            )
            if result is None:
                # 取数失败或者新用户未能入库，本轮跳过该公会
                continue

            inserted, changed = result
            inserted_users += inserted
            changed_actions += changed
    finally:
        logger.disable_tqdm()

    # 到期总数与本轮处理数之差即积压量：受容器容量限制而本轮未能排上的公会
    logger.info(
        'Schedule - Due: %s | Consumed: %s | Waiting: %s',
        refresh_plan.counter.due,
        refresh_plan.counter.pending,
        refresh_plan.counter.waiting
    )
    if inserted_users or changed_actions:
        logger.info(
            'Summary - Inserted: %s | Changed: %s',
            inserted_users,
            changed_actions
        )
