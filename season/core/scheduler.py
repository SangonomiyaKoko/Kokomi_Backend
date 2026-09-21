import gc
import json
import time
import psutil
import asyncio
import traceback

import redis
import pymysql
import requests
from shard import RedisKeys, ServicesName

from ..logger import logger, write_exception
from ..settings import (
    REGION,
    DATA_DIR,
    MEM_MONITOR,
    SSL_CA_BUNDLE,
    MYSQL_CONFIG,
    REDIS_CONFIG,
    REFRESH_INTERVAL
)

from .context import RunContext


def read_season_data() -> dict:
    """从本地 JSON 文件读取当前赛季配置数据"""
    file_path = DATA_DIR / 'json/clan_season.json'
    if not file_path.exists():
        return {"id": 0, "start": None, "finish": None}

    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def create_resources(run_ctx: RunContext) -> None:
    """创建所有需要的资源连接"""
    run_ctx.redis_client = redis.Redis(**REDIS_CONFIG)
    run_ctx.mysql_connection = pymysql.connect(**MYSQL_CONFIG)
    run_ctx.session = requests.Session()
    if SSL_CA_BUNDLE:
        # 处理俄服接口证书效验问题
        run_ctx.session.verify = SSL_CA_BUNDLE

    season = read_season_data()
    run_ctx.season_id = season['id']
    run_ctx.season_config = (season['start'], season['finish'])

    # 设置当前服务状态
    run_ctx.set_status_key()


def cleanup_resources(run_ctx: RunContext) -> None:
    """清理资源连接"""
    session = getattr(run_ctx, 'session', None)
    redis_client = getattr(run_ctx, 'redis_client', None)
    mysql_connection = getattr(run_ctx, 'mysql_connection', None)

    if session:
        session.close()
    if redis_client:
        redis_client.close()
    if mysql_connection:
        mysql_connection.close()


async def run_once() -> None:
    """执行一次完整更新循环并清理本轮资源"""
    # 避免可能的循环导入
    from .worker import run_worker

    run_ctx = RunContext()
    try:
        # 初始化资源
        create_resources(run_ctx)

        if REGION == 'ru':
            # 俄服不执行该服务并直接设置永久 Key
            status_key = RedisKeys.services(ServicesName.SEASON)
            run_ctx.redis_client.set(
                name=status_key,
                value=1
            )
            return 

        # 执行工作任务
        await run_worker(run_ctx)

    except Exception as e:
        error_name = type(e).__name__
        error_id = write_exception(
            error_type="ProgramError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
        logger.error(f"Fatal error: {error_name} - {error_id}")
        try:
            if getattr(run_ctx, 'redis_client', None):
                run_ctx.del_status_key()
        except Exception as e:
            logger.error(f'Failed to delete status key: {type(e).__name__}')
    finally:
        cleanup_resources(run_ctx)


async def start_scheduler(pid: int) -> None:
    """主调度器"""
    process = None
    # MEM_MONITOR 模式下监控内存占用趋势
    if MEM_MONITOR:
        process = psutil.Process(pid)

    while True:
        start = time.monotonic()

        await run_once()

        gc.collect()

        if process:
            logger.info(
                'Memory usage: %.2f MB',
                process.memory_info().rss / 1024 / 1024,
            )

        if REGION == 'ru':
            # 在设置好 key 后直接退出，没必要占用资源
            # 在实际生产环境中俄服节点就只会运行一次该脚本
            # 防止在统一检测状态时将该服务标记为离线
            return

        elapsed = time.monotonic() - start
        logger.info('This loop took %.2f seconds', round(elapsed, 2))

        sleep_time = max(1, round(REFRESH_INTERVAL - elapsed, 2))
        if sleep_time >= 1:
            logger.info(f'The process sleeps for {sleep_time} seconds')
            await asyncio.sleep(sleep_time)

        logger.info('-'*70)
