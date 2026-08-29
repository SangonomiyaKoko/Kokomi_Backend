
from context import UpdateContext
from clients import FetchResult
from models import (
    SkipReason,
    DisableReason,
    ValidationResult,
    UpdateStrategy,
    BattleMode

)
from settings import (
    REGION,
    USER_INACTIVE_DAYS,
    USER_NO_BATTLE_DAYS,
    USER_HIDDEN_PROFILE_DAYS,
)

class ValidationPolicy:
    """用户数据与响应的校验策略合集"""

    @staticmethod
    def validate_database_pre(ctx: UpdateContext) -> ValidationResult:
        """校验用户数据库状态"""
        if ctx.user_stats is None:
            return ValidationResult.skip(SkipReason.NO_LOCAL_DATA)

        # 用户在本地库中已被停用
        if not ctx.user_stats.is_valid:
            return ValidationResult.disabled(DisableReason.USER_DISABLED)

        # 用户从未有过战斗记录
        if ctx.user_stats.last_battle_at is None:
            return ValidationResult.disabled(DisableReason.USER_NO_BATTLE_RECORD)

        if ctx.user_record is None:
            return ValidationResult.skip(SkipReason.NO_LOCAL_DATA)

        if not ctx.user_record.is_configured:
            return ValidationResult.skip(SkipReason.NOT_CONFIGURED)

        return ValidationResult.other()

    @staticmethod
    def validate_response_pre(ctx: UpdateContext, fr: FetchResult) -> ValidationResult:
        """校验账号基础信息响应"""
        basic_data = fr.account.get(str(ctx.account_id))
        # API 响应中无此账号
        if basic_data is None:
            return ValidationResult.disabled(DisableReason.ACCOUNT_NOT_FOUND)

        if 'hidden_profile' in basic_data:
            if ctx.update_strategy == UpdateStrategy.NEW_USER:
                return ValidationResult.disabled(DisableReason.USER_HIDDEN)
            return ValidationResult.other()

        # 账号存在但缺少统计数据字段
        if 'statistics' not in basic_data:
            return ValidationResult.disabled(DisableReason.ACCOUNT_NO_STATS)

        for mode, types in fr.ships.items():
            for response in types.values():
                api_data = response.get(str(ctx.account_id))
                # 正常情况下先通过 Basic 接口校验，后续 mode 下的数据不应出现以下情况，因此判断为网络请求异常
                if api_data is None:
                    return ValidationResult.skip(SkipReason.OBTAIN_DATA_FAILED)
                if 'hidden_profile' in api_data:
                    return ValidationResult.skip(SkipReason.OBTAIN_DATA_FAILED)
                if mode == BattleMode.CLAN and REGION != 'ru':
                    continue
                if 'statistics' not in api_data:
                    return ValidationResult.skip(SkipReason.OBTAIN_DATA_FAILED)

        return ValidationResult.other()

    @classmethod
    def validate_database_post(cls, ctx: UpdateContext) -> ValidationResult:
        """校验用户是否满足保留条件"""
        # last_query_at 超过 USER_INACTIVE_DAYS 天
        if cls._is_inactive(ctx):
            return ValidationResult.disabled(DisableReason.USER_INACTIVE)

        # 连续隐藏战绩天数 ≥ USER_HIDDEN_PROFILE_DAYS
        if cls._is_hidden_too_long(ctx):
            return ValidationResult.disabled(DisableReason.USER_HIDDEN_TOO_LONG)

        # last_battle_at 超过 USER_NO_BATTLE_DAYS 天
        if cls._is_battle_inactive(ctx):
            return ValidationResult.disabled(DisableReason.USER_NO_BATTLE)

        return ValidationResult.other()

    @staticmethod
    def validate_response_post(ctx: UpdateContext) -> ValidationResult:
        """校验解析后的响应数据"""
        # 解析后用户状态仍无效，防御性兜底
        if not ctx.user_stats.is_valid:
            return ValidationResult.disabled(DisableReason.USER_INVALID)

        # 不应该出现新用户但是当前隐藏战绩的情况，直接丢弃
        if (
            ctx.update_strategy == UpdateStrategy.NEW_USER and 
            ctx.user_stats.is_hidden
        ):
            return ValidationResult.disabled(DisableReason.USER_HIDDEN)

        # 隐藏战绩没有数据，提前直接跳过
        if ctx.user_stats.is_hidden:
            return ValidationResult.other()

        # 确保数据完整性
        for mode in ctx.fetch_modes:
            mode_stats = ctx.latest_data[mode].mode
            collection = ctx.latest_data[mode].ship
            # 确保 mode_stats 无统计数据时，船只数据合集也没有统计数据
            if mode_stats.battles == 0:
                if collection.count == 0:
                    continue
                return ValidationResult.skip(SkipReason.OBTAIN_DATA_FAILED)
            if collection.count == 0:
                if mode_stats.battles == 0:
                    continue
                return ValidationResult.skip(SkipReason.OBTAIN_DATA_FAILED)
            
        return ValidationResult.other()

    @staticmethod
    def _is_inactive(ctx: UpdateContext) -> bool:
        """判断用户是否超过 USER_INACTIVE_DAYS 天无调用记录"""
        query_interval = ctx.query_interval
        if query_interval is None:
            return True

        return query_interval >= USER_INACTIVE_DAYS * 86400

    @staticmethod
    def _is_battle_inactive(ctx: UpdateContext) -> bool:
        """判断用户是否超过 USER_NO_BATTLE_DAYS 天无战斗记录"""
        if ctx.user_stats.is_hidden:
            # 用户隐藏战绩则读取不到正确的 LBT 时间
            return False

        battle_interval = ctx.battle_interval
        if battle_interval is None:
            return True

        return battle_interval >= USER_NO_BATTLE_DAYS * 86400

    @staticmethod
    def _is_hidden_too_long(ctx: UpdateContext) -> bool:
        """连续隐藏战绩天数是否达到 USER_HIDDEN_PROFILE_DAYS 阈值"""
        if not ctx.user_stats.is_hidden:
            return False

        # 从最新日期向前遍历 daily_summary，统计连续 is_public=False 的天数
        hidden_streak = 0
        for date in ctx.dates_desc:
            summary = ctx.daily_summary.get(date)
            if summary is None or not summary.is_public:
                hidden_streak += 1
            else:
                break

        return hidden_streak >= USER_HIDDEN_PROFILE_DAYS
