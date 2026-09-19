from __future__ import annotations

from enum import Enum, auto


class BattleMode(Enum):
    """战斗模式"""
    PVP = 1
    RANK = 2
    CLAN = 3

    def __str__(self) -> str:
        return self.name


class DataType(Enum):
    """数据类型"""
    SOLO = 1
    DIV2 = 2
    DIV3 = 3

    def __str__(self) -> str:
        return self.name

class UpdateStrategy(Enum):
    """根据本地数据库确定更新 daily_summary 表时的策略"""
    # 正常更新流程，本地数据库中一定存在当前日期下的 summary 数据
    # 策略：仅 UPDATE 当前日期下的 summary 数据
    NORMAL = 1

    # 数据库初始化流程，本地数据库没有数据，需要读取全量数据
    # 策略：需要 INSERT 今日和昨日两个日期下的 summary 数据，确保今日的增量数据被纳入统计
    NEW_USER = 2          # 本地没有缓存数据，需要全量初始化

    # 特殊更新流程，今日和昨日的 summary 均缺失或均为隐藏战绩，缺失多由服务崩溃导致
    # 策略：需要 UPDATE 今日和昨日两个日期下的 summary 数据，确保今日的增量数据被纳入统计
    MISSING_SUMMARY = 3   # 今日和昨日的 summary 均缺失或均为隐藏战绩，需同时更新昨日和今日 summary

    # 特殊更新流程，由于用户之前配置 AC 导致无法记录 CLAN 模式数据
    # 策略：在 UPDATE 当前日期下的 summary 数据的同时，将 CLAN 模式数据插入昨日的 summary 数据中
    SPECIAL_CLAN_UPDATE = 4 # 特殊更新情况

    def __str__(self) -> str:
        return self.name

class UpdateAction(Enum):
    """更新动作"""
    FAILED = auto()
    SKIPPED = auto()
    DISABLED = auto()
    CONTINUE = auto()

class FailedReason(Enum):
    OBTAIN_DATA_FAILED = "ObtainDataFailed"
    ACQUIRE_LOCK_FAILED = "AcquireLockFailed"
    DB_OPERATION_FAILED = "DbOperationFailed"
    MYSQL_REFRESH_FAILED = "MySQLRefreshFailed"

class UpdatedReason(Enum):
    """更新原因"""
    CONTINUE = "Continue"
    FIRST_UPDATE = "FirstUpdate"
    STATS_CHANGED = "StatsChanged"
    FALLBACK_REFRESH = "FallbackRefresh"

class SkippedReason(Enum):
    """跳过原因"""
    USER_HIDDEN = "UserHidden"
    NOT_CONFIGURED = "NotConfigured"  # 未从 MySQL 中读取到有效数据
    STATS_UNCHANGED = "StatsUnchanged"
    HIDDEN_PROFILE = "HiddenProfile"
    NO_FETCH_MODES = "NoFetchModes"

class DisabledReason(Enum):
    """禁用原因"""
    USER_HIDDEN = "UserHidden"    # 首次更新不允许隐藏战绩状态
    ACCOUNT_INVALID = "AccountInvalid"    # 账号无效或已被停用
    ACCOUNT_NO_STATS = "AccountNoStats"   # 账号存在但无战斗数据
    DATA_INTEGRITY_ERROR = "DataIntegrityError"  # 数据库完整性效验失败

    USER_INACTIVE_TOO_LONG = "UserInactiveTooLong"       # 账号长时间未被查询
    ACCOUNT_HIDDEN_TOO_LONG = "AccountHiddenTooLong"     # 账号长时间保持隐藏战绩状态
    ACCOUNT_INACTIVE_TOO_LONG = "AccountInactiveTooLong" # 账号长时间未有战斗数据
    

class RunnerResult(Enum):
    FAILED = auto()
    SKIPPED = auto()
    UPDATED = auto()
    DISABLED = auto()