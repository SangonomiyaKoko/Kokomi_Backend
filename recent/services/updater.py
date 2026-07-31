from loggers import logger
from settings import USER_REFRESH_TIMEOUT
from utils import TimeUtils
from db import sqlite_transaction, ensure_database
from models import UpdateContext
from repository import (
    DailySummaryRepository, 
    ShipCacheRepository
)


from .policy import (
    PreValidationPolicy,
    PostValidationPolicy
)
from .result import (
    SkipReason,
    UpdateReason,
    UpdateResult, 
    ValidationResult
)



class RefreshCoordinator:
    """用户 SQLite 数据库的流程协调者"""

    @classmethod
    def main(cls, ctx: UpdateContext) -> UpdateResult:
        """检测用户是否需要触发数据刷新，同时处理用户校验与停用"""
        # 先效验 user_stats 和 user_record 有效
        pre = PreValidationPolicy.validate(ctx)
        if pre.is_skip:
            return UpdateResult.skip(pre.reason)
        if pre.is_disabled:
            return UpdateResult.disabled(pre.reason)

        # 确保 SQLite 数据库文件存在并已初始化
        init_result = cls._prepare(ctx)
        if not init_result:
            return UpdateResult.skip(SkipReason.DB_OPERATION_FAILED)
        
        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                # 加载用户所有的 daily_summary 数据
                cls._load_data(cursor, ctx)

                # 补全缺失的 daily_summary 列
                cls._repair(cursor, ctx)

                # 基于用户的 daily_summary 数据判断用户是否需要更新
                need_update = cls._evaluate(cursor, ctx)
        except Exception:
            return UpdateResult.skip(SkipReason.DB_OPERATION_FAILED)

        # 检测账号是否符合保留条件
        post = PostValidationPolicy.validate(ctx)
        if post == ValidationResult.is_disabled:
            return UpdateResult.disabled(post.reason)

        # 保底更新检查：如果上游未按时触发刷新，则基于用户等级的超时配置兜底触发更新
        need_update = cls._check_fallback(ctx, need_update)

        return need_update

    @staticmethod
    def _prepare(ctx: UpdateContext) -> bool:
        """确保 SQLite 数据库文件存在并已初始化"""
        return ensure_database(ctx.account_id)

    @staticmethod
    def _load_data(cursor, ctx: UpdateContext) -> None:
        """从 SQLite 加载 daily_summary 并生成完整的日期列表"""
        # 加载用户所有的 daily_summary 和 ship_cache 数据
        ctx.ship_cache = ShipCacheRepository.load_all(cursor)
        daily_summary = DailySummaryRepository.load_all(cursor)
        if daily_summary == {}:
            return

        # 生成从最早日期开始的完整连续的日期列表
        ctx.date_list = TimeUtils.get_reset_date_list(
            current_timestamp=ctx.current_timestamp,
            start_date=min(daily_summary.keys()),
        )

        # 生成完整且连续的 summary 数据
        result = {}
        for d in ctx.dates_desc:
            result[d] = daily_summary.get(d)
        ctx.daily_summary = result

    @staticmethod
    def _repair(cursor, ctx: UpdateContext) -> None:
        """检查 daily_summary 的日期连续性，用上一条记录填充缺失日期"""
        last_summary_date = None
        
        # 从旧往新的日期顺序开始遍历
        for date in ctx.dates_asc:
            data = ctx.daily_summary.get(date)
            if data:
                last_summary_date = date
                continue
            
            if last_summary_date is None:
                logger.warning(f'{ctx.account_id} | Fix row {date} failed')
                continue

            # 如果日期下的数据为 None，则从上一个日期取数据补全该数据
            prev = ctx.daily_summary[last_summary_date]
            DailySummaryRepository.insert(cursor, date, prev)
            ctx.daily_summary[date] = prev

    @staticmethod
    def _evaluate(cursor, ctx: UpdateContext) -> bool:
        """基于更新策略判定是否需要触发刷新"""
        stats = ctx.user_stats

        # 本地没有 summary 数据
        if not ctx.has_any_summary:
            if stats.is_hidden:
                summary = DailySummaryRepository.hidden(stats.updated_at)
                DailySummaryRepository.insert(cursor, ctx.yesterday_date, summary)
                DailySummaryRepository.insert(cursor, ctx.now_date, summary)
                return UpdateResult.skip(SkipReason.USER_HIDDEN)
    
            if stats.no_competitive:
                summary = DailySummaryRepository.from_stats(stats, None)
                DailySummaryRepository.insert(cursor, ctx.yesterday_date, summary)
                DailySummaryRepository.insert(cursor, ctx.now_date, summary)
                return UpdateResult.skip(SkipReason.NO_COMPETITIVE_STATS)
    
            return UpdateResult.need_update(UpdateReason.FIRST_UPDATE)
        
        summary = ctx.latest_summary
        # 确保 latest_summary 记录存在
        if not summary:
            logger.error(f'{ctx.account_id} | Missing latest summary')
            return UpdateResult.skip(SkipReason.UNEXPECTED_ERROR)

        # 用户当前隐藏战绩
        if stats.is_hidden:
            if (
                summary.is_public and 
                TimeUtils.get_reset_date(summary.updated_at) != ctx.now_date
            ):
                # 当前 summary 数据存在战绩但是更新数据时间非当前日期，则更新 summary 数据
                hidden = DailySummaryRepository.hidden(stats.updated_at)
                DailySummaryRepository.update(cursor, ctx.now_date, hidden)
            elif (
                not summary.is_public and 
                stats.is_cache_outdated(summary.updated_at)
            ):
                # 当前 summary 数据隐藏战绩，但更新数据时间可更新，则更新 summary 数据
                hidden = DailySummaryRepository.hidden(stats.updated_at)
                DailySummaryRepository.update(cursor, ctx.now_date, hidden)
            return UpdateResult.skip(SkipReason.USER_HIDDEN)

        # 用户pvp和rank数据没有发生变动
        if stats.is_stats_unchanged(summary.pvp_battles, summary.ranked_battles):
            if stats.is_cache_outdated(summary.updated_at):
                updated = DailySummaryRepository.from_stats(stats, summary.index_table)
                DailySummaryRepository.update(cursor, ctx.now_date, updated)
            return UpdateResult.skip(SkipReason.STATS_UNCHANGED)

        return UpdateResult.need_update(UpdateReason.STATS_CHANGED)

    @staticmethod
    def _check_fallback(ctx: UpdateContext, current_result: UpdateResult) -> UpdateResult:
        """保底更新检查：当上游未按时触发刷新时，基于用户等级的容忍超时时间兜底触发更新"""
        next_refresh_at = ctx.user_record.next_refresh_at
        if next_refresh_at is None:
            return current_result

        # 如果已经判定需要更新，无需再做保底检查
        if current_result.is_need_update:
            return current_result

        # 获取当前用户等级对应的超时容忍时间
        level_key = str(ctx.user_record.user_level)
        timeout = USER_REFRESH_TIMEOUT.get(level_key)
        if timeout is None:
            return current_result

        # 当前时间已超过 next_refresh_at + timeout，触发保底更新
        if ctx.current_timestamp > next_refresh_at + timeout:
            return UpdateResult.need_update(UpdateReason.FALLBACK_REFRESH)

        return current_result
