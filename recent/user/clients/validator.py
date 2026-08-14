from __future__ import annotations

from models import (
    ValidationResult,
    SkipReason,
    DisableReason,
    UpdateContext,
    UpdateStrategy
)

from .requester import FetchResult


class ResponseValidator:
    """效验API返回数据是否符合预期"""

    @staticmethod
    def main(ctx: UpdateContext, fr: FetchResult) -> ValidationResult:
        """效验账号基础信息响应"""
        basic_data = fr.account.get(str(ctx.account_id))
        if basic_data is None:
            return ValidationResult.disabled(DisableReason.USER_INVALID)
        
        if 'hidden_profile' in basic_data:
            if ctx.update_strategy == UpdateStrategy.NEW_USER:
                return ValidationResult.disabled(DisableReason.USER_HIDDEN)
            return ValidationResult.other()

        if 'statistics' not in basic_data:
            return ValidationResult.disabled(DisableReason.USER_INVALID)

        for types in fr.ships.values():
            for response in types.values():
                api_data = response.get(str(ctx.account_id))
                # 正常来说先通过Basic接口数据效验后，后续mode下的数据不应该出现以下情况，因此判断为网络请求异常导致的
                if api_data is None:
                    return ValidationResult.skip(SkipReason.OBTAIN_DATA_FAILED)
                if 'hidden_profile' in api_data:
                    return ValidationResult.skip(SkipReason.OBTAIN_DATA_FAILED)
                if 'statistics' not in api_data:
                    return ValidationResult.skip(SkipReason.OBTAIN_DATA_FAILED)

        return ValidationResult.other()
