from __future__ import annotations

from typing import Optional, Union
from dataclasses import dataclass

from .mode import (
    BattleMode,
    UpdateAction,
    SkipReason,
    UpdateReason,
    DisableReason
)


@dataclass
class ValidationResult:
    """用户校验流程的执行结果"""
    action: UpdateAction
    reason: Optional[SkipReason | DisableReason] = None

    @classmethod
    def skip(cls, reason: SkipReason) -> ValidationResult:
        """创建跳过结果"""
        return cls(action=UpdateAction.SKIP, reason=reason)

    @classmethod
    def disabled(cls, reason: DisableReason) -> ValidationResult:
        """创建禁用结果"""
        return cls(action=UpdateAction.DISABLED, reason=reason)

    @classmethod
    def other(cls) -> ValidationResult:
        """创建继续执行结果"""
        return cls(action=UpdateAction.CONTINUE, reason=None)

    @property
    def is_skip(self) -> bool:
        """判断当前结果是否为跳过"""
        return self.action == UpdateAction.SKIP

    @property
    def is_disabled(self) -> bool:
        """判断当前结果是否为禁用"""
        return self.action == UpdateAction.DISABLED

@dataclass
class UpdateResult:
    """用户更新流程的执行结果"""
    action: UpdateAction
    reason: Union[SkipReason, DisableReason, UpdateReason]
    modes: Optional[set[BattleMode]] = None

    @classmethod
    def need_update(
        cls, reason: UpdateReason, modes: set[BattleMode] | None = None
    ) -> UpdateResult:
        """创建需要更新结果"""
        return cls(action=UpdateAction.NEED_UPDATE, reason=reason, modes=modes)

    @classmethod
    def skip(cls, reason: SkipReason) -> UpdateResult:
        """创建跳过结果"""
        return cls(action=UpdateAction.SKIP, reason=reason)

    @classmethod
    def disabled(cls, reason: DisableReason) -> UpdateResult:
        """创建禁用结果"""
        return cls(action=UpdateAction.DISABLED, reason=reason)

    @property
    def is_need_update(self) -> bool:
        """判断当前结果是否需要更新"""
        return self.action == UpdateAction.NEED_UPDATE

    @property
    def is_skip(self) -> bool:
        """判断当前结果是否为跳过"""
        return self.action == UpdateAction.SKIP

    @property
    def is_disabled(self) -> bool:
        """判断当前结果是否为禁用"""
        return self.action == UpdateAction.DISABLED

    @property
    def reason_text(self) -> str:
        """获取原因文本"""
        if self.reason is None:
            return ""
        return self.reason.value
