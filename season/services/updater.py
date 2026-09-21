import traceback
from typing import Optional
from pathlib import Path

from shard import (
    MySQLOPS,
    SQLiteOPS,
    RedisKeys,
    ClanBattleUtils
)

from ..core import RunContext, UpdateContext
from ..models import TeamStats, BattleRecord, DEMOTION, PROMOTION
from ..repository import (
    ClanStatsRepository,
    ClanBattleRepository
)
from ..clients import APIRequester
from ..logger import logger, write_exception
from ..settings import REGION

from .parser import ClanStatsParser


class ClanSeasonUpdater:
    """单个公会的赛季数据更新流水线"""

    @classmethod
    def main(
        cls, run_ctx: RunContext, clan_id: int, season_file: Path
    ) -> None:
        """执行单个公会的完整更新流程"""
        # record 由阶段二按需生成，不作为构造参数传入
        ctx = UpdateContext(
            clan_id=clan_id,
            season_id=run_ctx.season_id
        )

        # 拉取公会详情并解析为标准化数据
        if not cls._fetch_stats(run_ctx, ctx):
            return

        # 对比本地缓存生成对战明细
        # 该行为仅计算差值数据，抛出异常也不应影响后续的数据写入
        try:
            cls._plan_record(ctx)
        except Exception as e:
            error_name = type(e).__name__
            error_id = write_exception(
                error_type="ProgramError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            logger.error(f'{clan_id} | {error_name} - {error_id}')

        # 提交数据库写入并刷新排行榜缓存
        cls._commit(run_ctx, ctx, season_file)
        run_ctx.redis_client.zadd(
            RedisKeys.clan_zrank(),
            {str(ctx.clan_id): ctx.stats.clan_rating}
        )
        # 仅在本轮数据确实入库后才计入统计
        run_ctx.record_match += ctx.record_inc
        run_ctx.discard_match += ctx.discard_inc

    @classmethod
    def _fetch_stats(
        cls, run_ctx: RunContext, ctx: UpdateContext
    ) -> bool:
        """拉取公会详情、解析并加载本地队伍缓存

        结果分别写入 ctx.stats 与 ctx.cache；任一环节异常时
        返回 False，本轮放弃该公会
        """
        try:
            raw_data = APIRequester.fetch_clan_info(
                session=run_ctx.session,
                redis_client=run_ctx.redis_client,
                clan_id=ctx.clan_id
            )
            if not raw_data:
                logger.info(f'{ctx.clan_id} | Failed to obtain data')
                return False

            ctx.stats = ClanStatsParser.main(
                season_id=ctx.season_id,
                clan_id=ctx.clan_id,
                raw_data=raw_data
            )
            
            # 加载本地缓存的旧队伍数据
            with MySQLOPS.read_only(run_ctx.mysql_connection) as cursor:
                ctx.cache = ClanStatsRepository.load_team_cache(cursor, ctx.clan_id)
        except Exception as e:
            error_name = type(e).__name__
            error_id = write_exception(
                error_type="ProgramError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            logger.error(f'{ctx.clan_id} | {error_name} - {error_id}')
            return False

        return True

    @classmethod
    def _plan_record(
        cls, ctx: UpdateContext
    ) -> None:
        """对比缓存与最新数据，生成对战明细"""
        if ctx.cache is None:
            # 理论上不应该存在缺失 T_clan_team 数据的情况
            logger.error(f'{ctx.clan_id} | Missing local data')
            return
        
        if ctx.cache.season != ctx.season_id:
            # 缓存中的 season 与当前赛季不符，说明本地没有本赛季的初始化基线
            ctx.discard_inc = (
                ctx.stats.team_alpha.battles_count +
                ctx.stats.team_bravo.battles_count
            )
            return

        # 计算两份数据之间的场次差值
        alpha_battles_diff = max(
            ctx.stats.team_alpha.battles_count -
            ctx.cache.team_alpha.battles_count,
            0
        )
        bravo_battles_diff = max(
            ctx.stats.team_bravo.battles_count -
            ctx.cache.team_bravo.battles_count,
            0
        )
        battles_diff = alpha_battles_diff + bravo_battles_diff
        
        if battles_diff == 0:
            # 没有新增场次，无需生成对战明细
            return

        if battles_diff > 1:
            # 由于 LBT 仅记录最新 team 的数据
            # 因此为了确保记录的数据的准确, 对增量大于 1 的数据不做记录
            ctx.discard_inc = battles_diff
            return
        
        try:
            # battles_diff 为 1，说明新增场次只来自其中一支队伍
            team_num = 1 if alpha_battles_diff == 1 else 2
            new_team, old_team = (
                (ctx.stats.team_alpha, ctx.cache.team_alpha)
                if team_num == 1
                else (ctx.stats.team_bravo, ctx.cache.team_bravo)
            )
            # 由战斗发生时间反推所处的时间区间，而非取当前时间
            # 保底刷新等场景下轮次可能已在窗口之外，取当前时间会得到错误的区间
            time_window = ClanBattleUtils.get_window_index(
                region=REGION,
                timestamp=ctx.stats.last_battle_time
            )
            ctx.record = cls._plan_team(
                clan_id=ctx.clan_id,
                team_num=team_num,
                new_data=new_team,
                old_data=old_team,
                last_battle_time=ctx.stats.last_battle_time,
                time_window=time_window
            )

            ctx.record_inc = 1
            return
        except Exception:
            # 避免计算异常导致数据丢失
            ctx.discard_inc = 1
            raise

    @staticmethod
    def _plan_team(
        clan_id: int,
        team_num: int,
        new_data: TeamStats,
        old_data: TeamStats,
        last_battle_time: int,
        time_window: Optional[int]
    ) -> BattleRecord:
        """生成单个队伍的对战明细"""
        wins_diff = new_data.wins_count - old_data.wins_count
        rating_diff = new_data.public_rating - old_data.public_rating

        if new_data.stage_type and new_data.stage_progress:
            # 晋级or保级赛详情
            result = f'+{new_data.stage_progress[-1]}'
        elif new_data.league != old_data.league:
            # 晋级或者降级，league 越低对应的段位越高
            if new_data.league > old_data.league:
                result = DEMOTION
            else:
                result = PROMOTION
        elif rating_diff != 0:
            # 评分变动
            if rating_diff > 0:
                result = f'+{rating_diff}'
            elif rating_diff < 0:
                result = str(rating_diff)
        else:
            # 未知情况，评分未动
            result = '—'

        return BattleRecord(
            clan_id=clan_id,
            team_number=team_num,
            victory=wins_diff,
            result=result,
            rating=new_data.public_rating,
            league=new_data.league,
            division=new_data.division,
            division_rating=new_data.division_rating,
            stage_type=new_data.stage_type,
            stage_progress=new_data.stage_progress,
            time_window=time_window,
            battle_time=last_battle_time
        )

    @staticmethod
    def _commit(
        run_ctx: RunContext, ctx: UpdateContext, season_file: Path
    ) -> None:
        """提交本次更新"""
        # 先写 MySQL 确保即使 SQLite 数据库写入失败不影响主数据库数据的完整
        with MySQLOPS.transaction(run_ctx.mysql_connection) as cursor:
            ClanStatsRepository.update_stats(cursor, ctx.stats)
            ClanStatsRepository.update_teams(cursor, ctx.stats)

        if not ctx.record:
            return
        
        with SQLiteOPS.transaction(season_file) as cursor:
            ClanBattleRepository.insert_battles(cursor, ctx.record)
