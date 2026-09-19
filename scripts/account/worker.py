from redis import Redis
from pymysql import Connection
from celery import Celery
from shard import (
    RedisKeys,
    CommonConfig,
    progress_iterable
)

from .logger import logger
from .log_ops import maintain_log_files
from .updater import (
    RefreshPlanStats,
    DueUserContainer
)
from .db_ops import (
    mysql_read_only,
    mysql_transaction,
    BasicDataRepository
)
from .settings import (
    BATCH_SIZE,
    QUEUE_LOCK_TTL,
    MAX_DISPATCH_PER_ROUND
)


def send_task(
    celery_app: Celery,
    task_name: str,
    entity_id: int,
    queue_name: str
) -> bool:
    """向指定队列发送 Celery 任务"""
    try:
        celery_app.send_task(
            name=task_name,
            args=[{'uid': entity_id}],
            queue=queue_name
        )
        return True
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Send Task failed: {entity_id} | {error_name}")
        return False


async def run_worker(
    mysql_conn: Connection,
    lock_client: Redis,
    celery_app: Celery
) -> None:
    """单轮维护调度执行体"""

    # 扫描全表，筛选出本轮需要更新的用户
    candidates = DueUserContainer(
        capacity=MAX_DISPATCH_PER_ROUND
    )
    refresh_plan = RefreshPlanStats()

    with mysql_read_only(mysql_conn) as cursor:
        # 读取自增 ID 列最大值作为终止值
        max_id = BasicDataRepository.load_max_id(cursor)

        if max_id == 0:
            logger.info("No local users")
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
                due_users = refresh_plan.add_batch(rows)
                if not due_users:
                    continue

                due_account_ids = list(due_users.keys())

                # 检查队列锁是否存在
                pipe = lock_client.pipeline()
                for account_id in due_account_ids:
                    pipe.exists(RedisKeys.queue_lock(account_id))
                existing_results = pipe.execute()

                pending_users = {
                    account_id: due_users[account_id]
                    for account_id, locked in zip(
                        due_account_ids, existing_results
                    ) if not locked
                }

                refresh_plan.counter.locked += len(due_users) - len(pending_users)

                # 排除仍在排队中的用户，其余交由容器按优先级保留最紧急的一批
                candidates.offer(pending_users)
        finally:
            logger.disable_tqdm()
            
    logger.info(
        'Planned user updates within today: %s',
        refresh_plan.today_remained_counts
    )

    # 平衡未来 24h 内的计划更新分布，并将统计结果写入数据库
    refresh_plan.rebalance_plan()
    with mysql_transaction(mysql_conn) as cursor:
        BasicDataRepository.write_stats(
            cursor=cursor,
            stats_data=refresh_plan.statistic()
        )

    # 分发 Celery 任务：先入队，入队成功后再加排队锁
    update_ids = candidates.get_account_ids()
    if len(update_ids) == 0:
        logger.info("No pending tasks")
        return

    refresh_plan.counter.pending = len(update_ids)

    failed_counts = 0

    logger.enable_tqdm()
    try:
        for account_id in progress_iterable(
            items=update_ids,
            entry='user',
            logger=logger,
            sample_print='Pending tasks'
        ):
            if not send_task(
                celery_app=celery_app,
                task_name=CommonConfig.REFRESH_TASK_NAME,
                entity_id=account_id,
                queue_name=CommonConfig.REFRESH_QUEUE_NAME
            ):
                failed_counts += 1
                continue

            # 入队成功后立即加锁，nx=True 保证不会覆盖其它未完成任务的锁
            # 单轮派发量上限即容器容量，逐个加锁的往返开销可以接受
            lock_client.set(
                name=RedisKeys.queue_lock(account_id),
                value=1,
                nx=True,
                ex=QUEUE_LOCK_TTL
            )
    finally:
        logger.disable_tqdm()

    # 到期总数与本轮派发数之差即积压量：包含仍在排队未消化的用户，
    # 以及受容器容量限制而本轮未能排上的用户
    logger.info(
        'Schedule - Due: %s | Locked: %s | Pending: %s | Waiting: %s',
        refresh_plan.counter.due,
        refresh_plan.counter.locked,
        refresh_plan.counter.pending,
        refresh_plan.counter.waiting
    )
    if failed_counts:
        logger.info('Task send failed:  %s', failed_counts)

    # 检查、转存和清理日志文件
    maintain_log_files()
