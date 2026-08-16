from __future__ import annotations

from db import sqlite_transaction
from utils import TimeUtils
from models import (
    UpdateContext,
    BattleMode,
    SnapshotUpdatePlan,
    UpdateStrategy,
    FULL_UPDATE_MODES
)
from repository import (
    DailySummaryRepository,
    ShipCacheRepository,
    ShipIndexDataRepository,
    ShipIndexMapRepository,
    RecentStatsRepository,
)

from .planner import UpdatePlanner


class UserRefresher:
    """用户近期战斗数据更新器"""

    @classmethod
    def main(cls, ctx: UpdateContext) -> str:
        """主入口：正常用户（含 MISSING_SUMMARY）"""
        # 隐藏战绩用户
        if ctx.user_stats.is_hidden:
            return cls._handle_hidden_user(ctx)

        # 根据本地数据与 API 数据比对确定写入
        plan = UpdatePlanner.build_plan(ctx)
        return cls._commit_changed(ctx, plan)

    @classmethod
    def _handle_hidden_user(cls, ctx: UpdateContext) -> str:
        """处理隐藏战绩用户：确保今日 daily_summary 为隐藏状态"""
        stats = ctx.user_stats
        try:
            summary = DailySummaryRepository.hidden(stats.updated_at)
            with sqlite_transaction(ctx.account_id) as cursor:
                if ctx.latest_summary.is_public:
                    if TimeUtils.get_reset_date(summary.updated_at) != ctx.now_date:
                        DailySummaryRepository.update(cursor, ctx.now_date, summary)
                else:
                    if stats.is_cache_outdated(ctx.latest_summary.updated_at):
                        DailySummaryRepository.update(cursor, ctx.now_date, summary)
        except Exception:
            return 'Exception'
        return 'Hidden'

    @classmethod
    def _commit_changed(cls, ctx: UpdateContext, plan: SnapshotUpdatePlan) -> str:
        """提交正常用户的更新数据（summary + map/data + latest_index + recent）"""
        indices = cls._build_mode_indices(ctx, plan)
        _indices = {
            BattleMode.PVP: indices.get(BattleMode.PVP)[1],
            BattleMode.RANK: indices.get(BattleMode.RANK)[1],
            BattleMode.CLAN: indices.get(BattleMode.CLAN)[1]
        }
        summary = DailySummaryRepository.from_stats(ctx.user_stats, _indices)
        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                cls._commit_plan(cursor, plan, indices)
                cls._write_summary(cursor, ctx, summary)
                RecentStatsRepository.insert(cursor, plan.recent_params)
        except Exception:
            return 'Exception'
        return 'Success'

    @classmethod
    def _build_mode_indices(cls, ctx: UpdateContext, plan: SnapshotUpdatePlan) -> dict[BattleMode, tuple]:
        """各模式 summary 索引：变更模式用新 map_index，未变更模式沿用旧索引"""
        indices = {}
        for mode, mode_plan in plan:
            if mode_plan.no_stats:
                indices[mode] = (0, 0)
            else:
                if mode == BattleMode.PVP:
                    battles = ctx.user_stats.pvp_battles
                elif mode == BattleMode.RANK:
                    battles = ctx.user_stats.ranked_battles
                else:
                    battles = ctx.user_stats.rating_battles
                indices[mode] = (battles, mode_plan.map_index)
        for mode in FULL_UPDATE_MODES:
            if mode not in indices:
                indices[mode] = (ctx.ship_cache.get_battle(mode), ctx.ship_cache.get_index(mode))
        return indices

    @staticmethod
    def _write_summary(cursor, ctx: UpdateContext, summary) -> None:
        """写入 summary：MISSING_SUMMARY 时同时写昨日与今日，避免丢失今日近期数据"""
        if ctx.update_strategy == UpdateStrategy.MISSING_SUMMARY:
            DailySummaryRepository.update(cursor, ctx.yesterday_date, summary)
        DailySummaryRepository.update(cursor, ctx.now_date, summary)

    @staticmethod
    def _commit_plan(cursor, plan: SnapshotUpdatePlan, indices: dict[BattleMode, tuple]) -> None:
        """按模式提交 map/data 行，并刷新船只缓存与特殊行"""
        for mode_plan in plan.modes.values():
            if not mode_plan.no_stats:
                ShipIndexMapRepository.refresh(cursor, mode_plan.map_params)
                ShipIndexDataRepository.refresh(cursor, mode_plan.data_params)
        ShipCacheRepository.record_latest_index(
            cursor,
            pvp=indices[BattleMode.PVP],
            rank=indices[BattleMode.RANK],
            clan=indices[BattleMode.CLAN]
        )
        ShipCacheRepository.refresh(cursor, plan.cache_params)
