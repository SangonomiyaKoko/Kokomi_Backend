from __future__ import annotations

from typing import Optional, Union
from dataclasses import dataclass

from .mode import (
    UpdateAction,
    FailedReason,
    SkippedReason,
    UpdatedReason,
    DisabledReason
)


@dataclass
class ValidationResult:
    """用户校验流程的执行结果"""
    action: UpdateAction
    reason: Optional[FailedReason | SkippedReason | DisabledReason] = None

    @classmethod
    def failed(cls, reason: FailedReason) -> ValidationResult:
        """创建失败结果"""
        return cls(action=UpdateAction.FAILED, reason=reason)

    @classmethod
    def skipped(cls, reason: SkippedReason) -> ValidationResult:
        """创建跳过结果"""
        return cls(action=UpdateAction.SKIPPED, reason=reason)

    @classmethod
    def disabled(cls, reason: DisabledReason) -> ValidationResult:
        """创建禁用结果"""
        return cls(action=UpdateAction.DISABLED, reason=reason)

    @classmethod
    def other(cls) -> ValidationResult:
        """创建继续执行结果"""
        return cls(action=UpdateAction.CONTINUE, reason=None)

    @property
    def is_failed(self) -> bool:
        """判断当前结果是否为失败"""
        return self.action == UpdateAction.FAILED

    @property
    def is_skipped(self) -> bool:
        """判断当前结果是否为跳过"""
        return self.action == UpdateAction.SKIPPED

    @property
    def is_disabled(self) -> bool:
        """判断当前结果是否为禁用"""
        return self.action == UpdateAction.DISABLED

@dataclass
class UpdateResult:
    """用户更新流程的执行结果"""
    action: UpdateAction
    reason: Union[FailedReason, SkippedReason, DisabledReason, UpdatedReason]

    @classmethod
    def failed(cls, reason: FailedReason) -> UpdateResult:
        """创建失败结果"""
        return cls(action=UpdateAction.FAILED, reason=reason)

    @classmethod
    def skipped(cls, reason: SkippedReason) -> UpdateResult:
        """创建跳过结果"""
        return cls(action=UpdateAction.SKIPPED, reason=reason)

    @classmethod
    def disabled(cls, reason: DisabledReason) -> UpdateResult:
        """创建禁用结果"""
        return cls(action=UpdateAction.DISABLED, reason=reason)

    @classmethod
    def other(cls, reason: UpdatedReason) -> UpdateResult:
        """创建需要更新结果"""
        return cls(action=UpdateAction.CONTINUE, reason=reason)

    @property
    def is_failed(self) -> bool:
        """判断当前结果是否为失败"""
        return self.action == UpdateAction.FAILED

    @property
    def is_skipped(self) -> bool:
        """判断当前结果是否为跳过"""
        return self.action == UpdateAction.SKIPPED

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
