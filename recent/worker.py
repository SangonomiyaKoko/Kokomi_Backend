from typing import Iterator
from contextlib import contextmanager

from redis import Redis
from pymysql import Connection

from loggers import TqdmAwareLogger, logger
from utils import TimeUtils
from models import UserStats
from context import UpdateContext
from db import fetch_recent_user_ids, fetch_user_record
from coordinator import UserUpdater
from processor import UserDataProcessor
from refresher import UserRefresher
from settings import USE_TQDM, SQLITE_DIR


@contextmanager
def recent_refresh_lock(
    redis_client: Redis, account_id: int
) -> Iterator[bool]:
    """用户级别的分布式锁，防止并发重复刷新同一用户。

    锁的 TTL 为 60 秒，超时自动释放以避免死锁。
    """
    lock_key = f"refresh_lock:recent:{account_id}"
    acquired = redis_client.set(lock_key, 1, nx=True, ex=60)

    if not acquired:
        logger.info(f'{account_id} | Failed to acquire lock')
        yield False
        return

    try:
        yield True
    finally:
        redis_client.delete(lock_key)


def progress_iterable(
    items: list, desc: str, logger_obj: TqdmAwareLogger
) -> Iterator:
    """遍历列表，tqdm 模式下用进度条，否则日志输出进度。"""
    if USE_TQDM:
        from tqdm import tqdm

        tqdm_desc = f'{TimeUtils.get_formatted_date()} [INFO] {desc}'
        with tqdm(items, desc=tqdm_desc, total=len(items)) as pbar:
            for item in pbar:
                pbar.set_postfix_str(str(item))
                yield item
    else:
        total = len(items)
        for idx, item in enumerate(items, 1):
            logger_obj.info(
                '%s - [%d/%d] | Current: %s', desc, idx, total, item
            )
            yield item


async def run_worker(
    mysql_connection: Connection,
    redis_client: Redis,
    async_client,
) -> None:
    """工作函数，遍历所有启用的用户并执行完整的更新流程。

    整体流程：
    1. 从 MySQL 获取所有启用的用户列表
    2. 逐用户读取配置与战绩快照
    3. 获取 Redis 分布式锁
    4. 通过 UserUpdater.main() 完成校验 + 停用 + 更新判定
    5. 调用外部 API 获取用户最新数据
    6. 通过 UserStatsSyncer.refresh() 刷新 MySQL
    7. 通过 UserRefresh.main() 更新 SQLite 近期数据
    """
    # 效验数据库文件路径是否合法
    marker_file= SQLITE_DIR / '_MOUNT_POINT'
    if not marker_file.exists():
        logger.warning(f'File {marker_file} missing')
        return
    
    disable_id_dict = {}
    # 读取所有需要更新的用户列表
    with mysql_connection.cursor() as cursor:
        update_list = fetch_recent_user_ids(cursor)

    logger.enable_tqdm()
    for account_id in progress_iterable(
        items=update_list,
        desc="Processing user",
        logger_obj=logger,
    ):
        timestamp = TimeUtils.get_current_timestamp()
        update_context = UpdateContext(
            redis_client=redis_client,
            async_client=async_client,
            mysql_connection=mysql_connection,
            current_timestamp=timestamp,
            account_id=account_id
        )

        with mysql_connection.cursor() as cursor:
            record, stats = fetch_user_record(cursor, account_id)
            update_context.user_record = record
            update_context.user_stats = stats

        with recent_refresh_lock(
            redis_client, account_id
        ) as locked:
            if not locked:
                logger.info(f'{account_id} | SKIP - AcqurieLockFailed')
                continue

            result = UserUpdater.main(update_context)
            if result.is_skip:
                logger.debug(f'{account_id} | SKIP - {result.reason_text}')
                continue
            if result.is_disabled:
                logger.debug(f'{account_id} | DISABLED - {result.reason_text}')
                disable_id_dict[account_id] = result.reason_text
                continue

            logger.debug(f'{account_id} | NEED_UPDATE - {result.reason_text}')

            result = UserDataProcessor.main(update_context)
            if result.is_skip:
                logger.debug(f'{account_id} | SKIP - {result.reason_text}')
                continue
            if result.is_disabled:
                logger.debug(f'{account_id} | DISABLED - {result.reason_text}')
                disable_id_dict[account_id] = result.reason_text
                continue

            refresh_result = await UserRefresher.main(update_context)
            logger.debug(f'{account_id} | UPDATED - {refresh_result}')

    logger.disable_tqdm()
