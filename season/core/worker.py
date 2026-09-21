from shard import (
    MySQLOPS, 
    SQLiteOPS, 
    ClanBattleUtils, 
    progress_iterable
)

from ..repository import (
    BasicDataRepository, 
    ClanBattleRepository
)
from ..services import (
    ClanBaseSyncer,
    LeagueCollector,
    ClanSeasonUpdater,
    ClanRankingWriter
)
from ..logger import logger
from ..settings import REGION, DATA_DIR, CREATE_SQL

from .context import RunContext


# T_tracking_meta 中记录本轮刷新状态的键
TRACKING_KEY = 'clan_season'
TRACKING_TYPE = 'refresh_time'


async def run_worker(run_ctx: RunContext) -> None:
    """ClanSeason 功能后台更新服务"""
    # 读取当前赛季信息
    if run_ctx.season_id == 0:
        logger.warning('Season_ID not configured')
        return
    
    logger.info(f'Current Season ID: {run_ctx.season_id}')

    # 保底每天刷新一次
    with MySQLOPS.read_only(run_ctx.mysql_connection) as cursor:
        need_update = BasicDataRepository.is_need_update(
            cursor=cursor, 
            tracking_key=TRACKING_KEY, 
            tracking_type=TRACKING_TYPE
        )

    # 检查是否处于 CLAN 模式活跃时间段
    if not need_update:
        need_update = ClanBattleUtils.is_cb_active(
            region=REGION,
            season_start=run_ctx.season_config[0],
            season_finish=run_ctx.season_config[1]
        )

    if not need_update:
        logger.info('Update time not yet reached')
        return

    failed = False
    try:
        # 收集所有联赛分段中的公会数据
        status = LeagueCollector.main(run_ctx)
        if not status:
            logger.info('League collection aborted')
            failed = True
            return
        
        # 确保当前赛季的对战数据库文件存在
        season_file = SQLiteOPS.season_db_path(DATA_DIR, run_ctx.season_id)
        if not SQLiteOPS.ensure_database(season_file, CREATE_SQL):
            raise ValueError('SQLite database file is abnormal')

        if len(run_ctx.clan_entries) == 0:
            # 理论上不应该出现无活跃工会的情况，默认为接口异常
            logger.warning('No active clans')
            return 

        # 同步公会基础数据并筛选出需要刷新详情的公会
        update_ids = ClanBaseSyncer.main(run_ctx)
        
        logger.info(f'Clans update numbers: {len(update_ids)}')

        if not update_ids:
            # 没有数据变动直接返回
            return

        logger.enable_tqdm()
        try:
            for clan_id in progress_iterable(
                items=update_ids,
                entry='clan',
                logger=logger
            ):
                ClanSeasonUpdater.main(run_ctx, clan_id, season_file)
        finally:
            logger.disable_tqdm()

        # 把记录到的场次和未记录到的场次写入数据库统计表中
        if run_ctx.record_match + run_ctx.discard_match > 0:
            with SQLiteOPS.transaction(season_file) as cursor:
                ClanBattleRepository.update_meta(
                    cursor=cursor,
                    record=run_ctx.record_match,
                    discard=run_ctx.discard_match
                )

        logger.info(
            'Summary - '
            f'Record: {run_ctx.record_match}  '
            f'Discard: {run_ctx.discard_match}'
        )

        # 只有存在数据变动的前提下才需要重新生成本轮的排行榜快照
        ClanRankingWriter.main(run_ctx)
    except Exception:
        failed = True
        raise
    finally:
        # 本轮更新全部完成后才写回追踪时间，避免中途失败被误判为已完成
        if not failed:
            with MySQLOPS.transaction(run_ctx.mysql_connection) as cursor:
                BasicDataRepository.update_tracking_key(
                    cursor=cursor, 
                    tracking_key=TRACKING_KEY, 
                    tracking_type=TRACKING_TYPE
                )
