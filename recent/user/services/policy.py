from models import UpdateContext
from models.result import (
    SkipReason,
    DisableReason,
    ValidationResult,
)
from settings import (
    USER_INACTIVE_DAYS,
    USER_NO_BATTLE_DAYS,
    USER_HIDDEN_PROFILE_DAYS,
)


class PreValidationPolicy:
    """load_data 前的快速校验"""
    @staticmethod
    def validate(ctx: UpdateContext) -> ValidationResult:
        if ctx.user_stats is None:
            return ValidationResult.skip(SkipReason.NO_LOCAL_DATA)
        
        if not ctx.user_stats.is_valid: 
            return ValidationResult.disabled(DisableReason.USER_INVALID)
        
        if ctx.user_stats.no_competitive: 
            return ValidationResult.disabled(DisableReason.USER_INVALID)

        if ctx.user_record is None:
            return ValidationResult.skip(SkipReason.NO_LOCAL_DATA)
        
        if not ctx.user_record.is_configured:
            return ValidationResult.skip(SkipReason.NOT_CONFIGURED)

        return ValidationResult.other()

class PostValidationPolicy:
    """load_data + repair 后的深度校验"""

    @staticmethod
    def validate(ctx: UpdateContext) -> ValidationResult:
        # last_query_at 超过 USER_INACTIVE_DAYS 天
        if PostValidationPolicy._is_inactive(ctx):
            return ValidationResult.disabled(DisableReason.USER_INACTIVE)
        
        # 连续隐藏战绩天数 ≥ USER_HIDDEN_PROFILE_DAYS
        if PostValidationPolicy._is_hidden_too_long(ctx):
            return ValidationResult.disabled(DisableReason.USER_HIDDEN_TOO_LONG)

        # last_battle_at 超过 USER_NO_BATTLE_DAYS 天
        if PostValidationPolicy._is_battle_inactive(ctx):
            return ValidationResult.disabled(DisableReason.USER_NO_BATTLE)

        return ValidationResult.other()

    @staticmethod
    def _is_inactive(ctx: UpdateContext) -> bool:
        """超过 USER_INACTIVE_DAYS 天无调用记录"""
        query_interval = ctx.query_interval
        if query_interval is None:
            return True
        
        return query_interval >= USER_INACTIVE_DAYS * 86400

    @staticmethod
    def _is_battle_inactive(ctx: UpdateContext) -> bool:
        """超过 USER_NO_BATTLE_DAYS 天无战斗记录"""
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
