from __future__ import annotations

from context import RunContext, UpdateContext
from models import (
    UpdateResult,
    SkipReason,
    UpdateReason
)
from clients import (
    EndpointRegistry,
    ApiRequester,
    ResponseParser
)

from .policy import ValidationPolicy
from .syncer import UserStatsSyncer


class UserDataProcessor:
    """负责用户数据请求、校验与领域模型构建"""

    @classmethod
    async def main(cls, ctx: UpdateContext, run_ctx: RunContext) -> UpdateResult:
        """请求并解析用户数据，同时同步 MySQL"""
        # 按需构建请求目标
        targets = EndpointRegistry.build_targets(ctx)

        # 并发请求
        fetch_result = await ApiRequester.fetch(ctx, run_ctx, targets)
        if not fetch_result:
            return UpdateResult.skip(SkipReason.OBTAIN_DATA_FAILED)

        # 同步 MySQL，记录更新时间戳
        update_timestamp = UserStatsSyncer.refresh(
            run_ctx.mysql_connection, ctx.account_id, fetch_result.account, True
        )
        if update_timestamp is None or isinstance(update_timestamp, str):
            return UpdateResult.skip(SkipReason.MYSQL_REFRESH_FAILED)
        ctx.update_timestamp = update_timestamp

        if len(ctx.fetch_modes) == 0:
            return UpdateResult.skip(SkipReason.NO_FETCH_MODES)

        # 校验 API 返回数据格式
        result = ValidationPolicy.validate_response_pre(ctx, fetch_result)
        if result.is_skip:
            return UpdateResult.skip(result.reason)
        if result.is_disabled:
            return UpdateResult.disabled(result.reason)

        # 解析并挂载领域模型
        ResponseParser.parse_response(ctx, fetch_result, update_timestamp)

        # 校验数据解析结果的结构完整性
        result = ValidationPolicy.validate_response_post(ctx)
        if result.is_skip:
            return UpdateResult.skip(result.reason)
        if result.is_disabled:
            return UpdateResult.disabled(result.reason)

        return UpdateResult.need_update(UpdateReason.CONTINUE)
