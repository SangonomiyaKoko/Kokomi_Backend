from redis import Redis
from pymysql import Connection
from celery import Celery
from shard import (
    MySQLOPS,
    RedisKeys,
    CommonConfig,
    RefreshPlanStats,
    DueEntityContainer,
    progress_iterable
)

from .logger import logger
from .log_ops import maintain_log_files
from .db_ops import BasicDataRepository
from .settings import (
    BATCH_SIZE,
    QUEUE_LOCK_TTL,
    REBALANCE_ENABLED,
    MAX_DISPATCH_PER_ROUND,
    REFRESH_ADVANCE_SECONDS,
    NEVER_REFRESHED_PRIORITY
)


def send_task(
    celery_app: Celery,
    task_name: str,
    entity_id: int,
    queue_name: str
) -> bool:
    """向指定队列发送 Celery 任务，返回是否发送成功"""
    try:
        celery_app.send_task(
            name=task_name,
            args=[{'uid': entity_id}],
            queue=queue_name
        )
        return True
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Send Task failed: {entity_id} - {error_name}")
        return False


async def run_worker(
    mysql_conn: Connection,
    lock_client: Redis,
    celery_app: Celery
) -> None:
    """单轮维护调度执行体"""

    # 清理过期日志文件
    maintain_log_files()

    candidates = DueEntityContainer(
        capacity=MAX_DISPATCH_PER_ROUND
    )
    refresh_plan = RefreshPlanStats(
        advance_seconds=REFRESH_ADVANCE_SECONDS,
        never_refreshed_priority=NEVER_REFRESHED_PRIORITY,
        distribution_len=10
    )

    with MySQLOPS.read_only(mysql_conn) as cursor:
        # 读取自增 ID 列最大值作为终止值
        max_id = BasicDataRepository.load_max_id(cursor)

        if max_id == 0:
            logger.info("No local users")
            return 

        logger.enable_tqdm()
        try:
            # 扫描全表，筛选出本轮需要更新的用户
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

                # 获取待更新用户 ID 列表用于后续去重
                due_account_ids = list(due_users.keys())

                # 检查用户 ID 队列锁是否存在
                # 该队列锁仅由本服务单线程写入，由消费者并发消费
                # 因此此时使用 exists 而非 setnx 确保后续先发送任务再设置队列锁的逻辑可靠
                # 以避免 setnx 后程序异常导致需要批量删除队列锁可能存在的数据一致性问题
                pipe = lock_client.pipeline()
                for account_id in due_account_ids:
                    pipe.exists(RedisKeys.queue_lock(account_id))
                existing_results = pipe.execute()

                # 筛选出未被加锁的待更新用户字典
                pending_users = {
                    account_id: due_users[account_id]
                    for account_id, locked in zip(
                        due_account_ids, existing_results
                    ) if not locked
                }

                # 被加锁用户 = 到期用户 - 未被加锁用户
                refresh_plan.counter.locked += len(due_users) - len(pending_users)

                # 交由待更新容器
                candidates.offer(pending_users)
        finally:
            logger.disable_tqdm()
            
    logger.info(
        'Planned user updates within today: %s',
        refresh_plan.today_remained_counts
    )

    # 平衡未来 24h 内的计划更新分布
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
        logger.info("No pending users")
        return

    # 分发 Celery 任务：先入队，入队成功后再加排队锁
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
                logger.warning(f'{account_id} | Task send failed')
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
