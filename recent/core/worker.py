from shard import RedisKeys, progress_iterable

from ..db_ops import mysql_read_only, refresh_lock
from ..models import RunnerResult
from ..repository import BasicDataRepository
from ..services import UserUpdateRunner
from ..logger import logger
from ..settings import SQLITE_DIR

from .context import RunContext


async def run_worker(
    run_ctx: RunContext
) -> None:
    """Recent 功能后台更新服务"""

    # 读取所有的计划用户列表
    with mysql_read_only(run_ctx.mysql_connection) as cursor:
        update_list = BasicDataRepository.load_user_ids(cursor)

    logger.enable_tqdm()
    try:
        i = 1
        for account_id in progress_iterable(
            items=update_list,
            entry='user',
            logger=logger
        ):
            # 效验用于表示服务状态的 Key 处于有效期内
            # 避免某个循环更新用户数量过多导致 Key 过期，定期维护其有效期
            if (
                i % 60 == 0 and 
                run_ctx.is_key_expiring()
            ):
                run_ctx.set_status_key()
            i += 1
            
            # 校验 SQLite 存储目录是否正确挂载，防止外挂云硬盘掉盘后误写入系统盘
            # 挂载丢失时目录仍可能存在，导致程序误判为首次初始化并创建新的数据库文件
            marker_file = SQLITE_DIR / '_MOUNT_POINT'  # _MOUNT_POINT 用于确认外挂云硬盘已正确挂载
            if not marker_file.exists():
                logger.error(f'Marker file not found: {marker_file}')
                raise RuntimeError('SQLite storage volume is not mounted correctly')

            # 用户计数
            run_ctx.run_counter.incr()

            # 获取分布式锁以避免并发写导致的问题
            recent_lock_key = RedisKeys.recent_lock(account_id)
            with refresh_lock(recent_lock_key, run_ctx.redis_client) as locked:
                if not locked:
                    logger.info(f'{account_id} | FAILED - AcquireLockFailed')
                    run_ctx.run_counter.record(RunnerResult.FAILED)
                    continue

                # 进入单个用户更新流程
                result = await UserUpdateRunner.run(run_ctx, account_id)

                # 记录指标
                run_ctx.run_counter.record(result)
    finally:
        logger.disable_tqdm()