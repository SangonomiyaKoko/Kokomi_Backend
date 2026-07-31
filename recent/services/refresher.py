from db import sqlite_transaction
from models import (
    UpdateContext,
    SnapshotUpdatePlan
)
from repository import (
    DailySummaryRepository,
    ShipCacheRepository,
    ShipSnapshotRepository,
    SnapshotIndexRepository,
    RecentStatsRepository
)

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
        plan = SnapshotManager.build_update_plan(ctx)

        # 全新用户（本地无任何 daily_summary 数据）
        if not ctx.has_any_summary:
            return cls._handle_new_user(ctx, plan)
        
        # 正常更新流程
        if not plan.is_changed:
            return cls._commit_no_changed(ctx, plan)
        else:
            return cls._commit_changed(ctx, plan)

    @classmethod
    def _handle_hidden_user(cls, ctx: UpdateContext) -> str:
        """处理隐藏战绩用户：确保今日 daily_summary 为隐藏状态"""
        hidden = DailySummaryRepository.hidden(ctx.user_stats.updated_at)

        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                if not ctx.has_any_summary:
                    DailySummaryRepository.insert(cursor, ctx.yesterday_date, hidden)
                    DailySummaryRepository.insert(cursor, ctx.now_date, hidden)
                else:
                    # 前文已确保当前日期的记录存在，因此直接更新
                    DailySummaryRepository.update(cursor, ctx.now_date, hidden)
        except Exception:
            return 'Exception'
        
        return 'Hidden'

    @classmethod
    def _handle_no_battle_user(cls, ctx: UpdateContext) -> str:
        """处理无 PVP / Rank 战绩用户：仅更新 daily_summary，不处理船只数据"""
        summary = DailySummaryRepository.from_stats(ctx.user_stats, None)
        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                if not ctx.has_any_summary:
                    DailySummaryRepository.insert(cursor, ctx.yesterday_date, summary)
                    DailySummaryRepository.insert(cursor, ctx.now_date, summary)
                else:
                    # 前文已确保当前日期的记录存在，因此直接更新
                    DailySummaryRepository.update(cursor, ctx.now_date, summary)
        except Exception:
            return 'Exception'

        return 'NoData'

    @classmethod
    def _handle_new_user(cls, ctx: UpdateContext, plan: SnapshotUpdatePlan) -> str:
        """提交全新用户数据：写入昨日+今日 summary、快照索引、船只缓存和快照"""
        summary = DailySummaryRepository.from_stats(ctx.user_stats, plan.table)
        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                DailySummaryRepository.insert(cursor, ctx.yesterday_date, summary)
                DailySummaryRepository.insert(cursor, ctx.now_date, summary)
                SnapshotIndexRepository.refresh(cursor, plan.index)
                ShipCacheRepository.refresh(cursor, plan.count, plan.table, plan.cache)
                ShipSnapshotRepository.refresh(cursor, plan.snapshot)
        except Exception:
            return 'Exception'

        return 'NewUser'


    @classmethod
    def _commit_no_changed(
        cls, ctx: UpdateContext, plan: SnapshotUpdatePlan,
    ) -> str:
        """提交正常用户的更新数据"""
        summary = DailySummaryRepository.from_stats(ctx.user_stats, plan.table)
        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                DailySummaryRepository.update(cursor, ctx.now_date, summary)
        except Exception:
            return 'Exception'

        return 'NoChanged'


    @classmethod
    def _commit_changed(
        cls, ctx: UpdateContext, plan: SnapshotUpdatePlan,
    ) -> str:
        """提交正常用户的更新数据"""
        summary = DailySummaryRepository.from_stats(ctx.user_stats, plan.table)
        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                DailySummaryRepository.update(cursor, ctx.now_date, summary)
                SnapshotIndexRepository.refresh(cursor, plan.index_params)
                ShipCacheRepository.refresh(cursor, plan.count, plan.table, plan.cache_params)
                ShipSnapshotRepository.refresh(cursor, plan.snapshot_params)
                RecentStatsRepository.insert(cursor, plan.recent_params)
        except Exception:
            return 'Changed'

        return 'Success'