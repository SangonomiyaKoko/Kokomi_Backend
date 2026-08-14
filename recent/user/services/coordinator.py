from __future__ import annotations

from loggers import logger
from settings import REGION, USER_REFRESH_TIMEOUT
from utils import TimeUtils
from db import sqlite_transaction, ensure_database
from models import (
    UpdateContext, 
    BattleMode, 
    UpdateStrategy,
    UpdateResult,
    SkipReason,
    UpdateReason,
    DisableReason,
    FULL_UPDATE_MODES,
    BASE_UPDATE_MODES
)
from repository import DailySummaryRepository, ShipCacheRepository

from .policy import PreValidationPolicy, PostValidationPolicy


class RefreshCoordinator:
    """用户 SQLite 数据库的流程协调者

    负责：校验与停用、数据加载、更新判定，以及确定本次需要请求哪些模式。
    """

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
                # 加载用户所有的 daily_summary 与 latest_index 数据
                load_result = cls._load_data(cursor, ctx)
                if not load_result:
                    return UpdateResult.disabled(DisableReason.DATA_INTEGRITY_ERROR)
                
                # 补全缺失的 daily_summary 日期
                cls._repair(cursor, ctx)

                # 判定是否需要更新，并产出需要请求的模式集合
                need_update = cls._evaluate(cursor, ctx)
        except Exception:
            return UpdateResult.skip(SkipReason.DB_OPERATION_FAILED)

        # 检测账号是否符合保留条件
        post = PostValidationPolicy.validate(ctx)
        if post.is_disabled:
            return UpdateResult.disabled(post.reason)

        # 保底更新检查：如果上游未按时触发刷新，则基于用户等级的超时配置兜底触发更新
        need_update = cls._check_fallback(ctx, need_update)

        return need_update

    @staticmethod
    def _prepare(ctx: UpdateContext) -> bool:
        """确保 SQLite 数据库文件存在并已初始化"""
        return ensure_database(ctx.account_id)

    @staticmethod
    def _load_data(cursor, ctx: UpdateContext) -> bool:
        """从 SQLite 加载 daily_summary 与 latest_index 数据，返回是否加载成功"""
        # 读取本地数据库的最新缓存数据
        ctx.ship_cache = ShipCacheRepository.load_all(cursor)
        daily_summary_dict = DailySummaryRepository.load_all(cursor)

        is_cache_null = ctx.ship_cache.is_new_user
        is_summary_null = len(daily_summary_dict) == 0
        
        # 新用户策略：需要 INSERT 两条 summary 记录
        if is_summary_null and is_cache_null:
            ctx.update_strategy = UpdateStrategy.NEW_USER
            return True

        # 不应该存在summary或者cache只有一项为None的情况
        if (
            (is_summary_null and not is_cache_null) or
            (not is_summary_null and is_cache_null)
        ):
            return False

        # 不应该存在只有一行summary数据的情况
        if len(daily_summary_dict) == 1:
            return False

        # 生成从最早日期开始的完整连续的日期列表
        ctx.date_list = TimeUtils.get_reset_date_list(
            current_timestamp=ctx.current_timestamp,
            start_date=min(daily_summary_dict.keys()),
        )

        # 生成完整且连续的 summary 数据，后续通过值是否为 None 来查找缺失列
        result = {}
        for d in ctx.dates_desc:
            result[d] = daily_summary_dict.get(d)

        # 更新异常策略：需要 UPDATE 两条 summary 记录
        if (
            result.get(ctx.now_date) is None and 
            result.get(ctx.yesterday_date) is None
        ):
            # 正常更新情况下不应该存在昨日 summary 记录的情况，只有后台服务崩溃导致缺失更新可能导致
            # 为避免记录不到今日的新增数据，写入数据的时候需要同时更新两条记录
            ctx.update_strategy = UpdateStrategy.MISSING_SUMMARY
        
        ctx.daily_summary = result

        return True

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
                logger.error(f'{ctx.account_id} | Fix row {date} failed')
                continue

            # 如果日期下的数据为 None，则从上一个日期取数据补全该数据
            prev = ctx.daily_summary[last_summary_date]
            DailySummaryRepository.insert(cursor, date, prev)
            ctx.daily_summary[date] = prev

        if (
            last_summary_date and
            not ctx.daily_summary[ctx.now_date].is_public and
            not ctx.daily_summary[ctx.yesterday_date].is_public
        ):
            # 近期连续隐藏战绩策略：需要 UPDATE 两条 summary 记录
            # 与 MISSING_SUMMARY 处理方式一致（同时写昨日+今日），故复用同一策略
            ctx.update_strategy = UpdateStrategy.MISSING_SUMMARY

    @staticmethod
    def _evaluate(cursor, ctx: UpdateContext) -> UpdateResult:
        """基于更新策略判定是否需要触发刷新"""
        stats = ctx.user_stats

        # 用户当前隐藏战绩
        if stats.is_hidden:
            summary = DailySummaryRepository.hidden(stats.updated_at)
            # 不应该对出现新用户但是当前隐藏战绩的情况
            if ctx.update_strategy == UpdateStrategy.NEW_USER:
                return UpdateResult.disabled(DisableReason.USER_HIDDEN)
            
            if ctx.latest_summary.is_public:
                if TimeUtils.get_reset_date(summary.updated_at) != ctx.now_date:
                    # 当前 summary 数据存在战绩但是更新数据时间非当前日期，则更新 summary 数据
                    DailySummaryRepository.update(cursor, ctx.now_date, summary)
            else:
                if stats.is_cache_outdated(ctx.latest_summary.updated_at):
                    # 当前 summary 数据隐藏战绩，但更新数据时间可更新，则更新 summary 数据
                    DailySummaryRepository.update(cursor, ctx.now_date, summary)
            return UpdateResult.skip(SkipReason.USER_HIDDEN)

        # 新用户首次强制全量更新，必须确保后续更新中数据库中有所有模式的完整快照数据
        if ctx.update_strategy == UpdateStrategy.NEW_USER:
            if REGION == 'ru':
                return UpdateResult.need_update(UpdateReason.FIRST_UPDATE, {BattleMode.PVP, BattleMode.RANK, BattleMode.CLAN})
            else:
                return UpdateResult.need_update(UpdateReason.FIRST_UPDATE, {BattleMode.PVP, BattleMode.RANK})

        # 正常用户，检测模式变更，确实实际需要更新的模式
        fetch_modes = set()
        local_cache = ctx.ship_cache
        if stats.pvp_battles != local_cache.get_battle(BattleMode.PVP):
            fetch_modes.add(BattleMode.PVP)
        if stats.ranked_battles != local_cache.get_battle(BattleMode.RANK):
            fetch_modes.add(BattleMode.RANK)
        if REGION == 'ru':
            if stats.rating_battles != local_cache.get_battle(BattleMode.CLAN):
                fetch_modes.add(BattleMode.CLAN)

        # 各模式均未变更，沿用旧索引
        if not fetch_modes:
            indices = {
                BattleMode.PVP: local_cache.get_index(BattleMode.PVP),
                BattleMode.RANK: local_cache.get_index(BattleMode.RANK),
                BattleMode.CLAN: local_cache.get_index(BattleMode.CLAN)
            }
            summary = DailySummaryRepository.from_stats(stats, indices)
            DailySummaryRepository.update(cursor, ctx.now_date, summary)
            return UpdateResult.skip(SkipReason.STATS_UNCHANGED)

        return UpdateResult.need_update(UpdateReason.STATS_CHANGED, fetch_modes)

    @staticmethod
    def _check_fallback(ctx: UpdateContext, current_result: UpdateResult) -> UpdateResult:
        """保底更新检查：当上游未按时触发刷新时，基于用户等级的容忍超时时间兜底触发更新"""
        next_refresh_at = ctx.user_record.next_refresh_at
        if next_refresh_at is None:
            return current_result

        # 如果已经判定需要更新，无需再做保底检查
        if current_result.is_need_update:
            return current_result

        # 跳过用户隐藏战绩的情况
        if ctx.user_stats.is_hidden:
            return current_result

        # 获取当前用户等级对应的超时容忍时间
        level_key = str(ctx.user_record.user_level)
        timeout = USER_REFRESH_TIMEOUT.get(level_key)
        if timeout is None:
            return current_result

        # 当前时间已超过 next_refresh_at + timeout，触发保底更新
        if ctx.current_timestamp > next_refresh_at + timeout:
            modes = FULL_UPDATE_MODES if REGION == 'ru' else BASE_UPDATE_MODES
            return UpdateResult.need_update(UpdateReason.FALLBACK_REFRESH, modes)

        return current_result
