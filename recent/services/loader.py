from dataclasses import replace
from sqlite3 import Cursor

from loggers import logger
from settings import REGION
from context import UpdateContext
from utils import TimeUtils
from params import LocalDataEntry
from db import sqlite_transaction, ensure_database
from models import (
    BattleMode,
    SkipReason,
    UpdateReason,
    DisableReason,
    UpdateResult,
    UpdateStrategy,
    FULL_UPDATE_MODES
)
from repository import (
    ShipLatestRepository,
    ModeLatestRepository,
    UserSummaryRepository
)

from .policy import ValidationPolicy


class UserDataLoader:
    """加载用户 SQLite 数据库的数据"""

    @classmethod
    def main(cls, ctx: UpdateContext) -> UpdateResult:
        """检测用户是否需要触发数据刷新，同时处理用户校验与停用"""
        # 先校验 user_stats 和 user_record 数据有效
        pre = ValidationPolicy.validate_database_pre(ctx)
        if pre.is_skip:
            return UpdateResult.skip(pre.reason)
        if pre.is_disabled:
            return UpdateResult.disabled(pre.reason)

        # 确保 SQLite 数据库文件存在并已初始化
        if not ensure_database(ctx.account_id):
            return UpdateResult.skip(SkipReason.DB_OPERATION_FAILED)

        # 从本地数据库中加载用户缓存数据
        try:
            with sqlite_transaction(ctx.account_id) as cursor:
                # 加载更新所必要的数据
                load_result = cls._load_data(cursor, ctx)
                if not load_result:
                    return UpdateResult.disabled(DisableReason.DATA_INTEGRITY_ERROR)

                # 补全缺失的 daily_summary 日期
                cls._repair(cursor, ctx)
        except Exception:
            return UpdateResult.skip(SkipReason.DB_OPERATION_FAILED)

        # 检测账号是否符合保留条件
        post = ValidationPolicy.validate_database_post(ctx)
        if post.is_disabled:
            return UpdateResult.disabled(post.reason)

        return UpdateResult.need_update(UpdateReason.CONTINUE)

    @staticmethod
    def _load_data(cursor: Cursor, ctx: UpdateContext) -> bool:
        """从 SQLite 加载 summary 和 cache 数据，返回是否加载成功"""
        # 读取本地数据库的最新缓存数据，包括每船缓存和各模式最新索引
        ship_latest = ShipLatestRepository.load_all(cursor)
        mode_latest = ModeLatestRepository.load_all(cursor)
        daily_summary_dict = UserSummaryRepository.load_all(cursor)

        is_cache_null = all(
            latest.mode_index is None for latest in mode_latest.values()
        )
        is_summary_null = len(daily_summary_dict) == 0

        # 新用户策略：需要 INSERT 两条 summary 记录
        if is_summary_null and is_cache_null:
            ctx.update_strategy = UpdateStrategy.NEW_USER
            return True

        # 不应该存在 summary 或者 cache 只有一项为 None 的情况
        # 要么两项均存在，要么均为 None
        if (
            (is_summary_null and not is_cache_null) or
            (not is_summary_null and is_cache_null)
        ):
            return False

        # 不应该存在只有一行 summary 数据的情况
        if len(daily_summary_dict) == 1:
            return False

        local_data = {}
        for mode in FULL_UPDATE_MODES:
            local_data[mode] = LocalDataEntry(
                mode=mode_latest[mode],
                ship=ship_latest[mode]
            )
        ctx.local_data = local_data

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
            # 正常情况下不会缺失昨日 summary 记录，仅服务崩溃可能导致
            # 为避免记录不到今日的新增数据，需要同时更新昨日和今日两条记录
            ctx.update_strategy = UpdateStrategy.MISSING_SUMMARY

        ctx.daily_summary = result

        return True

    @staticmethod
    def _repair(cursor: Cursor, ctx: UpdateContext) -> None:
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
            if date == ctx.now_date and ctx.access_token:
                # 直营服的 CLAN 模式不支持通过令牌查询，因此需要将当前 clan_index 置为 NULL
                if prev.clan_index:
                    prev = replace(prev, clan_battles=0, clan_index=None)
            UserSummaryRepository.insert(cursor, date, prev)
            ctx.daily_summary[date] = prev

        if not last_summary_date:
            ctx.latest_summary = None
            return

        ctx.latest_summary = ctx.daily_summary[last_summary_date]

        if not ctx.user_stats.is_hidden and REGION in ['asia', 'eu', 'na']:
            if ctx.local_data[BattleMode.CLAN].battles > 0:
                new_stats = replace(
                    ctx.user_stats, 
                    rating_battles = ctx.local_data[BattleMode.CLAN].battles
                )
                ctx.user_stats = new_stats

        if ctx.update_strategy != UpdateStrategy.NORMAL:
            return

        if (
            not ctx.daily_summary[ctx.now_date].is_public and
            not ctx.daily_summary[ctx.yesterday_date].is_public
        ):
            # 近期连续隐藏战绩策略：需要 UPDATE 两条 summary 记录
            # 与 MISSING_SUMMARY 处理方式一致，同时写昨日和今日
            ctx.update_strategy = UpdateStrategy.MISSING_SUMMARY
            return

        if ctx.current_timestamp - ctx.latest_summary.updated_at > 2*86400:
            # 最新快照的最后一次更新时间超过 48 小时，该异常仅出现于本地测试和服务长时间离线情况
            # 与 MISSING_SUMMARY 处理方式一致，同时写昨日和今日
            ctx.update_strategy = UpdateStrategy.MISSING_SUMMARY
            return

        if (
            ctx.daily_summary[ctx.now_date].is_public and
            ctx.daily_summary[ctx.now_date].clan_index is None and
            ctx.daily_summary[ctx.yesterday_date].is_public and
            ctx.daily_summary[ctx.yesterday_date].clan_index is None
        ):
            ctx.update_strategy = UpdateStrategy.SPECIAL_CLAN_UPDATE
            return
