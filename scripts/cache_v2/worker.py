from redis import Redis
from httpx import AsyncClient
from pymysql import Connection
from shard import (
    MySQLOPS,
    progress_iterable
)

from .logger import logger
from .refresher import ShipPvpRefresher, UpdateContext
from .models import ShipBenchmark, ShipRecordUpdater
from .db_ops import BasicDataRepository


async def run_worker(
    mysql_conn: Connection,
    redis_client: Redis,
    async_client: AsyncClient
) -> None:
    """单轮船只 PvP 缓存更新调度执行体"""

    # 读取待更新用户与各项基准数据
    with MySQLOPS.read_only(mysql_conn) as cursor:
        pending_count = BasicDataRepository.get_pending_count(cursor)
        if pending_count == 0:
            logger.info('No pending users')
            return

        update_ids = BasicDataRepository.get_update_ids(cursor)
        records = ShipRecordUpdater(
            BasicDataRepository.get_ship_records(cursor)
        )
        benchmarks = ShipBenchmark(
            BasicDataRepository.get_ship_benchmarks(cursor)
        )
        version, version_start = BasicDataRepository.get_game_version(cursor)

    ctx = UpdateContext(
        mysql_conn=mysql_conn,
        redis_client=redis_client,
        async_client=async_client,
        records=records,
        benchmarks=benchmarks,
        version=version,
        version_start=version_start
    )

    logger.enable_tqdm()
    try:
        # 依次更新单个用户，单个用户失败不影响本轮其余用户
        for account_id in progress_iterable(
            items=update_ids,
            entry='user',
            logger=logger
        ):
            try:
                await ShipPvpRefresher.refresh(ctx=ctx, account_id=account_id)
            except Exception as e:
                error_name = type(e).__name__
                logger.error(f'{account_id} | {error_name}')
    finally:
        logger.disable_tqdm()

        # 无论本轮是否正常结束，都将被刷新的船只记录值写入数据库
        with MySQLOPS.transaction(mysql_conn) as cursor:
            BasicDataRepository.update_ship_records(
                cursor=cursor,
                rows=records.output()
            )

    logger.info(
        'Schedule - Due: %s | Consumed: %s | Waiting: %s',
        pending_count,
        len(update_ids),
        pending_count - len(update_ids)
    )
