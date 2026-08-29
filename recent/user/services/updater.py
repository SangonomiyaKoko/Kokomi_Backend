from dataclasses import replace

from context import UpdateContext, RunContext
from models import (
    BattleMode,
    SkipReason,
    UpdateReason,
    DisableReason,
    UpdateResult,
    UpdateStrategy,
    FULL_UPDATE_MODES,
    BASE_UPDATE_MODES

)
from utils import TimeUtils
from settings import REGION, USER_REFRESH_TIMEOUT

class UpdateEvaluate:
    """用户更新评估器，判定本次需要更新的模式"""

    @staticmethod
    def main(run_ctx: RunContext, ctx: UpdateContext) -> UpdateResult:
        """基于更新策略判定是否需要触发刷新"""
        stats = ctx.user_stats

        # 用户当前隐藏战绩
        if stats.is_hidden:
            # 不应该出现新用户但是当前隐藏战绩的情况，直接丢弃
            if ctx.update_strategy == UpdateStrategy.NEW_USER:
                return UpdateResult.disabled(DisableReason.USER_HIDDEN)

            # 按需将今日 summary 更新为隐藏状态
            if ctx.latest_summary.is_public:
                # 当前 summary 有战绩但更新时间非今日 → 更新为隐藏
                if TimeUtils.get_reset_date(stats.updated_at) != ctx.now_date:
                    ctx.update_plan.user_summary.set_update_params_from_hidden(ctx.now_date, ctx.update_timestamp)
            else:
                # 当前 summary 已是隐藏但更新时间过旧 → 刷新时间戳
                if stats.is_cache_outdated(ctx.latest_summary.updated_at):
                    ctx.update_plan.user_summary.set_update_params_from_hidden(ctx.now_date, ctx.update_timestamp)

            return UpdateResult.skip(SkipReason.USER_HIDDEN)

        # 新用户，首次强制全量更新，必须确保后续更新中数据库中有所有模式的完整快照数据
        if ctx.update_strategy == UpdateStrategy.NEW_USER:
            if REGION == 'cn':
                # 中国服未提供 CLAN 模式的接口
                return UpdateResult.need_update(UpdateReason.FIRST_UPDATE, BASE_UPDATE_MODES)
            elif REGION == 'ru':
                # 俄罗斯服 CLAN 模式的接口支持通过 ac 查询数据
                return UpdateResult.need_update(UpdateReason.FIRST_UPDATE, FULL_UPDATE_MODES)
            elif ctx.access_token:
                # 已配置 ac 的直营服用户默认当前隐藏战绩，跳过 CLAN 模式的更新
                # 直营服获取 CLAN 模式的接口不支持通过 ac 查询数据
                return UpdateResult.need_update(UpdateReason.FIRST_UPDATE, BASE_UPDATE_MODES)
            else:
                # 未隐藏战绩用户，正常读取所有的模式数据
                return UpdateResult.need_update(UpdateReason.FIRST_UPDATE, FULL_UPDATE_MODES)

        # 正常用户，检测模式变更以确定实际需要更新的模式
        fetch_modes = set()

        # 全服的 PVP 和 RANK 模式更新流程通用检测
        for mode in (BattleMode.PVP, BattleMode.RANK):
            if stats.battles_for(mode) != ctx.local_data[mode].battles:
                fetch_modes.add(mode)

        # CLAN 模式更新分支
        if REGION == 'ru':
            # 俄服记录 Rating 战数据
            if stats.battles_for(BattleMode.CLAN) != ctx.local_data[BattleMode.CLAN].battles:
                fetch_modes.add(BattleMode.CLAN)
        elif REGION != 'cn':
            # 直营服根据时间段和用户活跃度数据触发更新
            clan_mode = ctx.local_data[BattleMode.CLAN].mode
            if (
                run_ctx.period_start_ts and 
                not ctx.access_token and 
                (clan_mode.update_time or 0) <= run_ctx.period_start_ts
            ):
                # 活跃时间段内、未配置 AC 且未在活跃期间更新过的用户，才可能触发 CLAN 更新
                if (
                    ctx.user_stats.updated_at >= run_ctx.period_start_ts
                    and ctx.current_timestamp - ctx.user_stats.last_battle_at >= 36000
                ):
                    # 活跃时间段内更新过且近 10h 无战斗，仅刷新记录的更新时间戳
                    ctx.update_plan.mode_latest.set_special_params(ctx.current_timestamp)
                elif run_ctx.clan_update_count < 60:
                    # 每轮循环最多允许更新 60 个用户，避免打断其他正常用户的更新
                    fetch_modes.add(BattleMode.CLAN)
                    run_ctx.clan_update_count += 1

        if len(fetch_modes) > 0:
            return UpdateResult.need_update(UpdateReason.STATS_CHANGED, fetch_modes)

        # 保底更新检查：当上游未按时触发刷新时，基于用户等级的容忍超时时间兜底触发更新
        next_refresh_at = ctx.user_record.next_refresh_at
        if next_refresh_at and not stats.is_hidden:
            level_key = str(ctx.user_record.user_level)
            timeout = USER_REFRESH_TIMEOUT.get(level_key, 86400)
            if ctx.current_timestamp > next_refresh_at + timeout:
                # 强制更新一次基础模式数据 PVP 和 RANK
                return UpdateResult.need_update(UpdateReason.FALLBACK_REFRESH, set())

        # 跳过更新时间戳一致时重复更新
        if ctx.latest_summary.updated_at >= stats.updated_at:
            return UpdateResult.skip(SkipReason.STATS_UNCHANGED)

        # 复用原本的数据索引
        indices = {
            BattleMode.PVP: ctx.local_data[BattleMode.PVP].mode_index,
            BattleMode.RANK: ctx.local_data[BattleMode.RANK].mode_index,
            BattleMode.CLAN: ctx.local_data[BattleMode.CLAN].mode_index
        }

        # 未配置 AC 的前提下，直营服 CLAN 模式的 battles 数据需要从本地数据库中加载替换
        if REGION in ['asia', 'eu', 'na']:
            if ctx.access_token:
                indices[BattleMode.CLAN] = None
            else:
                new_stats = replace(
                    ctx.user_stats, 
                    rating_battles=ctx.local_data[BattleMode.CLAN].battles
                )
                ctx.user_stats = new_stats

        ctx.update_plan.user_summary.set_update_params_from_stats(ctx.now_date, stats, indices)

        return UpdateResult.skip(SkipReason.STATS_UNCHANGED)
