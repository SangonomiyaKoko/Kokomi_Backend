from dataclasses import replace

from shard import TimeUtils, UserPolicyUtils

from ..core import UpdateContext, RunContext
from ..models import (
    BattleMode,
    SkippedReason,
    UpdatedReason,
    DisabledReason,
    UpdateResult,
    UpdateStrategy,
    FULL_UPDATE_MODES,
    BASE_UPDATE_MODES

)
from ..settings import (
    TOKEN,
    REGION, 
    TIMEZONE
)

class UpdateEvaluate:
    """用户更新评估器，判定本次需要更新的模式"""

    @classmethod
    def main(
        cls, run_ctx: RunContext, ctx: UpdateContext
    ) -> UpdateResult:
        """基于更新策略判定是否需要触发刷新"""
        stats = ctx.user_stats

        # 用户当前隐藏战绩
        if stats.is_hidden:
            # 不应该出现新用户但是当前隐藏战绩，直接丢弃
            # 首次更新必须确保存在战绩数据用以写入数据库
            # 否则写入两条hidden记录即无意义又增加后续判断分支
            if ctx.update_strategy == UpdateStrategy.NEW_USER:
                return UpdateResult.disabled(DisabledReason.USER_HIDDEN)

            # 按需将今日 summary 更新为隐藏状态
            if ctx.latest_summary.is_public:
                # 当前 summary 有战绩但更新时间非今日 → 更新为隐藏
                update_date = TimeUtils.reset_date(TIMEZONE, stats.updated_at)
                if update_date != ctx.now_date:
                    ctx.update_plan.user_summary.set_update_params_from_hidden(ctx.now_date, stats.updated_at)
            else:
                # 当前 summary 已是隐藏但更新时间过旧 → 刷新时间戳
                if stats.is_cache_outdated(ctx.latest_summary.updated_at):
                    ctx.update_plan.user_summary.set_update_params_from_hidden(ctx.now_date, stats.updated_at)

            return UpdateResult.skipped(SkippedReason.USER_HIDDEN)

        # 新用户，首次强制全量更新，必须确保后续更新中数据库中有所有模式的完整快照数据
        if ctx.update_strategy == UpdateStrategy.NEW_USER:
            if REGION == 'cn' or TOKEN is None:
                # 中国服未提供 CLAN 模式的接口
                ctx.fetch_modes = BASE_UPDATE_MODES
                return UpdateResult.other(UpdatedReason.FIRST_UPDATE)
            elif REGION == 'ru':
                # 俄罗斯服 CLAN 模式的接口支持通过 ac 查询数据
                ctx.fetch_modes = FULL_UPDATE_MODES
                return UpdateResult.other(UpdatedReason.FIRST_UPDATE)
            elif ctx.access_token:
                # 已配置 ac 的直营服用户默认当前隐藏战绩，跳过 CLAN 模式的更新
                # 直营服获取 CLAN 模式的接口不支持通过 ac 查询数据
                ctx.fetch_modes = BASE_UPDATE_MODES
                return UpdateResult.other(UpdatedReason.FIRST_UPDATE)
            else:
                # 未隐藏战绩用户，正常读取所有的模式数据
                ctx.fetch_modes = FULL_UPDATE_MODES
                return UpdateResult.other(UpdatedReason.FIRST_UPDATE)

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
            need_update = cls._update_direct_clan(run_ctx, ctx)
            if need_update:
                fetch_modes.add(BattleMode.CLAN)
                run_ctx.clan_update_count += 1

        if len(fetch_modes) > 0:
            ctx.fetch_modes = fetch_modes
            return UpdateResult.other(UpdatedReason.STATS_CHANGED)

        # 保底更新检查：当上游未按时触发刷新时，基于用户等级的容忍超时时间兜底触发更新
        next_refresh_at = ctx.user_record.next_refresh_at
        if next_refresh_at and not stats.is_hidden:
            timeout = UserPolicyUtils.recent_fallback_timeout(ctx.user_record.user_level)
            if ctx.current_timestamp > next_refresh_at + timeout:
                # 触发强制更新策略
                return UpdateResult.other(UpdatedReason.FALLBACK_REFRESH)

        # 跳过更新时间戳一致时重复更新
        if ctx.latest_summary.updated_at >= stats.updated_at:
            return UpdateResult.skipped(SkippedReason.STATS_UNCHANGED)

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
                # 用 local_data 中的 CLAN battles 替换 stats 中的 rating_battles
                new_stats = replace(
                    ctx.user_stats, 
                    rating_battles=ctx.local_data[BattleMode.CLAN].battles
                )
                ctx.user_stats = new_stats

        # 更新 summary 数据
        ctx.update_plan.user_summary.set_update_params_from_stats(ctx.now_date, stats, indices)

        return UpdateResult.skipped(SkippedReason.STATS_UNCHANGED)

    @staticmethod
    def _update_direct_clan(
        run_ctx: RunContext,
        ctx: UpdateContext
    ) -> bool:
        """处理直营服的 CLAN 模式更新"""
        clan_mode = ctx.local_data[BattleMode.CLAN].mode

        if not run_ctx.period_start_ts:
            # 未在 CLAN 模式更新活跃期
            return False

        if not TOKEN or ctx.access_token:
            # 未配置接口 TOKEN 或者配置了用户 AC
            return False

        if (clan_mode.update_time or 0) > run_ctx.period_start_ts:
            # 在 CLAN 模式更新活跃期中有过更新数据
            return False
        
        if (
            ctx.user_stats.updated_at >= run_ctx.period_start_ts and 
            ctx.current_timestamp - ctx.user_stats.last_battle_at >= 36000
        ):
            # 如果在 CLAN 模式更新活跃期中有过更新，且用户 lbt 说明用户没有战斗数据在此期间
            # 则判断用户没有在本次 CLAN 模式中有过战斗记录，因此仅刷新数据的更新时间戳
            ctx.update_plan.mode_latest.set_special_params(ctx.current_timestamp)
            return False

        if run_ctx.clan_update_count < 60:
            return True

        return False
