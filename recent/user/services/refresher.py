from __future__ import annotations

from db import sqlite_transaction
from utils import TimeUtils
from models import (
    UpdateContext,
    BattleMode,
    SnapshotUpdatePlan,
    UpdateStrategy,
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
        """主入口：正常用户（含 MISSING_SUMMARY）根据本地数据与 API 数据比对确定写入"""
        # 隐藏战绩用户（防御性分支，正常情况下已在 coordinator 被 skip）
        if ctx.user_stats.is_hidden:
            return cls._handle_hidden_user(ctx)

        # 正常流程（含 MISSING_SUMMARY）：根据本地数据与 API 数据比对确定写入
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
        summary = DailySummaryRepository.from_stats(
            ctx.user_stats, cls._build_summary_indices(ctx, plan)
        )
        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                cls._write_summary(cursor, ctx, summary)
                cls._commit_plan(cursor, ctx, plan)
                RecentStatsRepository.insert(cursor, plan.recent_params)
        except Exception:
            return 'Exception'
        return 'Success'

    # ---------- 辅助 ----------

    @classmethod
    def _build_summary_indices(cls, ctx: UpdateContext, plan: SnapshotUpdatePlan) -> dict:
        """各模式 summary 索引：变更模式用新 map_index，未变更模式沿用旧索引"""
        indices = {}
        if ctx.latest_summary is not None:
            indices = {
                BattleMode.PVP: ctx.latest_summary.pvp_index,
                BattleMode.RANK: ctx.latest_summary.rank_index,
                BattleMode.CLAN: ctx.latest_summary.clan_index,
            }
        for mode, mode_plan in plan.modes.items():
            indices[mode] = mode_plan.map_index
        return indices

    @staticmethod
    def _mode_tuple(
        ctx: UpdateContext, plan: SnapshotUpdatePlan, mode: BattleMode
    ) -> tuple:
        """构造特殊行中某模式的 (battles, index)：
        变更模式用最新统计 + 新 map 索引；未请求模式沿用缓存原值"""
        if mode in plan.modes:
            if mode == BattleMode.PVP:
                battles = ctx.user_stats.pvp_battles
            elif mode == BattleMode.RANK:
                battles = ctx.user_stats.ranked_battles
            else:
                battles = ctx.user_stats.rating_battles
            index = plan.modes[mode].map_index
        else:
            battles = ctx.ship_cache.get_battle(mode)
            index = ctx.ship_cache.get_index(mode)
        return (battles, index)

    @staticmethod
    def _write_summary(cursor, ctx: UpdateContext, summary) -> None:
        """写入 summary：MISSING_SUMMARY 时同时写昨日与今日，避免丢失今日近期数据"""
        if ctx.update_strategy == UpdateStrategy.MISSING_SUMMARY:
            DailySummaryRepository.update(cursor, ctx.yesterday_date, summary)
        DailySummaryRepository.update(cursor, ctx.now_date, summary)

    @staticmethod
    def _commit_plan(cursor, ctx: UpdateContext, plan: SnapshotUpdatePlan) -> None:
        """按模式提交 map/data 行，并刷新船只缓存与特殊行"""
        for mode_plan in plan.modes.values():
            ShipIndexMapRepository.refresh(cursor, mode_plan.map_params)
            ShipIndexDataRepository.refresh(cursor, mode_plan.data_params)
        ShipCacheRepository.record_latest_index(
            cursor,
            pvp=UserRefresher._mode_tuple(ctx, plan, BattleMode.PVP),
            rank=UserRefresher._mode_tuple(ctx, plan, BattleMode.RANK),
            clan=UserRefresher._mode_tuple(ctx, plan, BattleMode.CLAN),
        )
        ShipCacheRepository.refresh(cursor, plan.cache_params)
