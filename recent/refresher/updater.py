from db import sqlite_transaction
from context import UpdateContext
from models import (
    DailySummary,
    DailySummaryRepository,
    ShipCacheRepository,
    ShipSnapshotRepository,
    SnapshotIndexRepository,
    RecentStatsRepository,
    SnapshotUpdatePlan
)
from utils import StringUtils

from .manager import SnapshotManager


class UserRefresher:
    """用户近期战斗数据更新器"""

    @classmethod
    async def main(cls, ctx: UpdateContext) -> str:
        """主入口：根据用户状态分派到不同的处理逻辑"""
        # 隐藏战绩用户
        if ctx.user_stats.is_hidden:
            return cls._handle_hidden_user(ctx)

        # 无竞技模式战绩用户（无 PVP / Rank 数据）
        if ctx.user_stats.no_competitive:
            return cls._handle_no_battle_user(ctx)

        # 生成船只快照更新计划
        plan = SnapshotManager.compare(ctx)

        # 全新用户（本地无任何 daily_summary 数据）
        if not ctx.has_any_summary:
            return cls._commit_new_user(ctx, plan)

        # 正常更新流程
        return cls._commit_update(ctx, plan)

    @classmethod
    def _handle_hidden_user(cls, ctx: UpdateContext) -> str:
        """处理隐藏战绩用户：确保今日 daily_summary 为隐藏状态"""
        hidden = DailySummary.hidden(ctx.user_stats.updated_at)

        with sqlite_transaction(ctx.account_id) as cursor:
            if not ctx.has_any_summary:
                # 完全无本地数据：插入昨日和今日
                DailySummaryRepository.insert(cursor, ctx.yesterday_date, hidden)
                DailySummaryRepository.insert(cursor, ctx.now_date, hidden)
            else:
                # 已有今日数据：更新
                DailySummaryRepository.update(cursor, ctx.now_date, hidden)

        return 'Hidden'

    @classmethod
    def _handle_no_battle_user(cls, ctx: UpdateContext) -> str:
        """处理无 PVP / Rank 战绩用户：仅更新 daily_summary，不处理船只数据"""
        summary = DailySummary.from_stats(ctx.user_stats, None)

        with sqlite_transaction(ctx.account_id) as cursor:
            if not ctx.has_any_summary:
                DailySummaryRepository.insert(cursor, ctx.yesterday_date, summary)
                DailySummaryRepository.insert(cursor, ctx.now_date, summary)
            else:
                DailySummaryRepository.update(cursor, ctx.now_date, summary)

        return 'NoData'

    @classmethod
    def _commit_new_user(cls, ctx: UpdateContext, plan: SnapshotUpdatePlan) -> str:
        """提交全新用户数据：写入昨日+今日 summary、快照索引、船只缓存和快照"""
        summary = DailySummary.from_stats(ctx.user_stats, plan.table)

        with sqlite_transaction(ctx.account_id) as cursor:
            DailySummaryRepository.insert(cursor, ctx.yesterday_date, summary)
            DailySummaryRepository.insert(cursor, ctx.now_date, summary)

            SnapshotIndexRepository.insert(
                cursor, plan.table, plan.count,
                StringUtils.ship_map_encode(plan.ship_map),
            )
            ShipCacheRepository.refresh(
                cursor, cls._prepare_cache_params(plan.cache),
            )
            ShipSnapshotRepository.refresh(
                cursor, cls._prepare_snapshot_params(plan.snapshot),
            )

        return 'NewUser'


    @classmethod
    def _commit_update(
        cls, ctx: UpdateContext, plan: SnapshotUpdatePlan,
    ) -> str:
        """提交正常用户的更新数据"""
        with sqlite_transaction(ctx.account_id) as cursor:
            summary = DailySummary.from_stats(ctx.user_stats, plan.table)
            if ctx.latest_summary is None:
                DailySummaryRepository.insert(cursor, ctx.now_date, summary)
            else:
                DailySummaryRepository.update(cursor, ctx.now_date, summary)

            if not plan.is_changed:
                return 'Success'
            
            SnapshotIndexRepository.refresh(cursor, plan.table, plan.count, plan.index)
            ShipCacheRepository.refresh(cursor, plan.cache)
            ShipSnapshotRepository.refresh(cursor, plan.snapshot)
            RecentStatsRepository.insert(cursor, plan.recent)

        return 'Success'