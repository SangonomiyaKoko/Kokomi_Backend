import traceback
from typing import Iterator
from contextlib import contextmanager

from loggers import logger, TqdmAwareLogger, write_exception
from utils import TimeUtils
from context import RunContext
from services import UserUpdateRunner
from db import (
    mysql_transaction,
    fetch_recent_user_ids,
    deactivate_user,
    remove_file
)
from settings import USE_TQDM, SQLITE_DIR, LOG_DIR


@contextmanager
def recent_refresh_lock(
    run_ctx: RunContext, account_id: int
) -> Iterator[bool]:
    """用户级别的分布式锁，防止并发重复刷新同一用户"""
    lock_key = f"refresh_lock:recent:{account_id}"
    # 任务理论上不存在超过 20s 的可能，因此设置 60s 过期时间防止死锁
    acquired = run_ctx.redis_client.set(lock_key, 1, nx=True, ex=60)

    if not acquired:
        logger.info(f'{account_id} | Failed to acquire lock')
        yield False
        return

    try:
        yield True
    finally:
        run_ctx.redis_client.delete(lock_key)


def delete_user_file(
    run_ctx: RunContext, account_id: int
) -> None:
    deletion_log_path = LOG_DIR / 'scripts' / 'UserDeletion.log'
    with mysql_transaction(run_ctx.mysql_connection, account_id=account_id) as cursor:
        deactivate_user(cursor, account_id)
    reason = run_ctx.disabled_users[account_id]
    try:
        remove_file(account_id)
    except Exception:
        logger.warning(f'{account_id} | Failed to remove local db file')
    line = (
        f'{TimeUtils.get_formatted_date()} [DELETE] '
        f'{account_id} | {reason}\n'
    )
    with open(deletion_log_path, mode='a', encoding='utf-8') as f:
        f.write(line)

def progress_iterable(
    items: list, desc: str, logger_obj: TqdmAwareLogger
) -> Iterator:
    """遍历列表，tqdm 模式下用进度条，否则日志输出进度"""
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


async def run_worker(run_ctx: RunContext) -> None:
    """Recent 功能后台更新服务"""

    # 读取所有需要更新的用户列表
    with run_ctx.mysql_connection.cursor() as cursor:
        update_list = fetch_recent_user_ids(cursor)

    # 主更新循环
    logger.enable_tqdm()
    try:
        for account_id in progress_iterable(
            items=update_list,
            desc="Processing user",
            logger_obj=logger,
        ):
            # 校验 SQLite 存储目录是否正确挂载，防止外挂云硬盘掉盘后误写入系统盘
            # 挂载丢失时目录仍可能存在，导致程序误判为首次初始化并创建新的数据库文件
            marker_file = SQLITE_DIR / '_MOUNT_POINT'  # _MOUNT_POINT 用于确认外挂云硬盘已正确挂载
            if not marker_file.exists():
                logger.error(f'Marker file not found: {marker_file}')
                raise RuntimeError('SQLite storage volume is not mounted correctly')

            # 获取分布式锁，避免并发写导致的问题
            with recent_refresh_lock(run_ctx, account_id) as locked:
                if not locked:
                    logger.info(f'{account_id} | SKIP - AcquireLockFailed')
                    continue

                try:
                    await UserUpdateRunner.run(run_ctx, account_id)
                except Exception as e:
                    error_name = type(e).__name__
                    logger.error(f'{account_id} | Failed: {type(e).__name__}')
                    write_exception(
                        error_type="ProgramError",
                        error_name=error_name,
                        error_info=traceback.format_exc()
                    )

                # 停用后再删除用户文件并记录日志
                if account_id in run_ctx.disabled_users:
                    delete_user_file(run_ctx, account_id)
    finally:
        logger.disable_tqdm()