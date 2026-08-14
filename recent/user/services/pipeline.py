from __future__ import annotations

from models import (
    UpdateContext,
    BattleMode,
    UpdateResult,
    SkipReason,
    UpdateReason
)
from clients import (
    EndpointRegistry,
    ApiRequester,
    ResponseValidator,
    ResponseParser
)

from .syncer import UserStatsSyncer


class UserDataProcessor:
    """负责用户数据请求、效验与领域模型构建"""

    @classmethod
    async def main(cls, ctx: UpdateContext) -> UpdateResult:
        # 按需构建请求目标
        targets = EndpointRegistry.build_targets(ctx)

        # 并发请求
        fetch_result = await ApiRequester.fetch(ctx, targets)
        if not fetch_result:
            return UpdateResult.skip(SkipReason.OBTAIN_DATA_FAILED)

        # 同步 MySQL
        update_timestamp = UserStatsSyncer.refresh(
            ctx.mysql_connection, ctx.account_id, fetch_result.account, True
        )
        if update_timestamp is None or isinstance(update_timestamp, str):
            return UpdateResult.skip(SkipReason.MYSQL_REFRESH_FAILED)

        # 效验返回数据
        result = ResponseValidator.main(ctx, fetch_result)
        if result.is_skip:
            return UpdateResult.skip(result.reason)
        if result.is_disabled:
            return UpdateResult.disabled(result.reason)

        # 解析并挂载领域模型
        ResponseParser.parse_response(ctx, fetch_result, update_timestamp)
        
        return UpdateResult.need_update(UpdateReason.CONTINUE)
