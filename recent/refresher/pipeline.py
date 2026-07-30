from models import (
    UserStats,
    UpdateContext,
    ShipDataCollection
)

from .syncer import UserStatsSyncer
from .fetcher import UserDataFetcher
from .result import (
    UpdateResult,
    SkipReason,
    DisableReason,
    UpdateReason,
    ValidationResult
)


class UserDataProcessor:
    """负责用户数据处理和效验"""

    @classmethod
    async def main(cls, ctx: UpdateContext) -> UpdateResult:
        responses = await UserDataFetcher.fetch_all(ctx)
        if not responses:
            return UpdateResult.skip(SkipReason.OBTAIN_DATA_FAILED)

        update_timestamp = UserStatsSyncer.refresh(ctx.mysql_connection, ctx.account_id, responses[0], True)
        if update_timestamp is None or isinstance(update_timestamp, str):
            return UpdateResult.skip(SkipReason.MYSQL_REFRESH_FAILED)

        result = cls._validate(ctx, responses)
        if result.is_skip:
            return UpdateResult.skip(result.reason)
        if result.is_disabled:
            return UpdateResult.disabled(result.reason)

        cls._process(ctx, responses, update_timestamp)
        return UpdateResult.need_update(UpdateReason.CONTINUE)
    
    @staticmethod
    def _validate(ctx: UpdateContext, responses: list) -> bool:
        """效验API响应是否合法"""
        basic_data = responses[0].get(str(ctx.account_id))
        if basic_data is None:
            return ValidationResult.disabled(DisableReason.USER_INVALID)
        
        is_public = 'hidden_profile' not in basic_data

        if not is_public:
            return ValidationResult.other()

        if 'statistics' not in basic_data:
            return ValidationResult.disabled(DisableReason.USER_INVALID)

        for response in responses[1:]:
            api_data = response.get(str(ctx.account_id))
            if 'hidden_profile' in api_data:
                return ValidationResult.skip(SkipReason.USER_HIDDEN)
            
            if (
                api_data is None or 
                'statistics' not in api_data
            ):
                return ValidationResult.disabled(DisableReason.USER_INVALID)
            
        return ValidationResult.other()
    
    @staticmethod
    def _process(ctx: UpdateContext, responses: list, update_timestamp: int) -> bool:
        """确保 SQLite 数据库文件存在并已初始化"""
        ctx.user_stats = UserStats.from_response(responses[0].get(str(ctx.account_id)), update_timestamp)
        if ctx.user_stats.is_public and not ctx.user_stats.no_competitive:
            ctx.ship_data = ShipDataCollection.from_responses(ctx.account_id, responses[1:])