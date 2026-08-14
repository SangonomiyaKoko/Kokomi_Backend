from __future__ import annotations

from enum import Enum, auto
from typing import Optional
from dataclasses import dataclass

from .mode import BattleMode


class UpdateAction(Enum):
    """更新动作"""
    CONTINUE = auto()
    NEED_UPDATE = auto()
    SKIP = auto()
    DISABLED = auto()

class SkipReason(Enum):
    """跳过原因"""
    NOT_CONFIGURED = "NotConfigured"
    DB_OPERATION_FAILED = "DbOperationFailed"
    NO_LOCAL_DATA = "NoLocalData"
    USER_HIDDEN = "UserHidden"
    STATS_UNCHANGED = "StatsUnchanged"
    NO_COMPETITIVE_STATS = "NoCompetitiveStats"
    OBTAIN_DATA_FAILED = "ObtainDataFailed"
    MYSQL_REFRESH_FAILED = "MySQLRefreshFailed"
    UNEXPECTED_ERROR = "UnexpectedError"

class DisableReason(Enum):
    """禁用原因"""
    USER_HIDDEN = "UserHidden"
    USER_INVALID = "UserInvalid"
    USER_INACTIVE = "UserInactive"
    USER_NO_BATTLE = "UserNoBattle"
    USER_HIDDEN_TOO_LONG = "UserHiddenTooLong"
    DATA_INTEGRITY_ERROR = "DataIntegrityError"

class UpdateReason(Enum):
    """更新原因"""
    CONTINUE = "Continue"
    FIRST_UPDATE = "FirstUpdate"
    STATS_CHANGED = "StatsChanged"
    FALLBACK_REFRESH = "FallbackRefresh"

@dataclass
class ValidationResult:
    """用户效验流程的执行结果"""
    action: UpdateAction
    reason: Optional[SkipReason | DisableReason] = None

    @classmethod
    def skip(cls, reason: SkipReason) -> ValidationResult:
        return cls(action=UpdateAction.SKIP, reason=reason)

    @classmethod
    def disabled(cls, reason: DisableReason) -> ValidationResult:
        return cls(action=UpdateAction.DISABLED, reason=reason)

    @classmethod
    def other(cls) -> ValidationResult:
        return cls(action=UpdateAction.CONTINUE, reason=None)

    @property
    def is_skip(self) -> bool:
        return self.action == UpdateAction.SKIP

    @property
    def is_disabled(self) -> bool:
        return self.action == UpdateAction.DISABLED

@dataclass
class UpdateResult:
    """用户更新流程的执行结果"""
    action: UpdateAction
    reason: Enum
    modes: Optional[set[BattleMode]] = None

    @classmethod
    def need_update(cls, reason: UpdateReason, modes: set = None) -> UpdateResult:
        return cls(action=UpdateAction.NEED_UPDATE, reason=reason, modes=modes)

    @classmethod
    def skip(cls, reason: SkipReason) -> UpdateResult:
        return cls(action=UpdateAction.SKIP, reason=reason)

    @classmethod
    def disabled(cls, reason: DisableReason) -> UpdateResult:
        return cls(action=UpdateAction.DISABLED, reason=reason)

    @property
    def is_need_update(self) -> bool:
        return self.action == UpdateAction.NEED_UPDATE

    @property
    def is_skip(self) -> bool:
        return self.action == UpdateAction.SKIP

    @property
    def is_disabled(self) -> bool:
        return self.action == UpdateAction.DISABLED

    @property
    def reason_text(self) -> str:
        """获取原因文本"""
        if self.reason is None:
            return ""
        return self.reason.value
