from redis import Redis
from httpx import AsyncClient
from pymysql import Connection
from typing import Dict, List, Set
from dataclasses import dataclass, field

from utils import TimeUtils
from params import (
    UserSummaryLocalEntry,
    LocalDataEntry,
    UpdatePlan
)
from models import (
    LatestDataEntry,
    UserRecord,
    UserStats,
    UpdateStrategy,
    BattleMode
)


@dataclass
class RunContext:
    """整轮循环的上下文"""
    redis_client: Redis = field(init=False)
    async_client: AsyncClient = field(init=False)
    mysql_connection: Connection = field(init=False)

    period_start_ts: int = field(init=False)
    clan_update_count: int = field(init=False, default=0)
    disabled_users: dict[int, str] = field(
        default_factory=dict
    )  # 被禁用用户 → 原因

    def __post_init__(self) -> None:
        self.period_start_ts = TimeUtils.is_cb_active()

    def __str__(self) -> str:
        return (
            f"RunContext("
            f"redis_client={id(self.redis_client)}, "
            f"async_client={id(self.async_client)}, "
            f"mysql_connection={id(self.mysql_connection)}, "
            f"period_start_ts={self.period_start_ts}, "
            f"clan_update_count={self.clan_update_count}, "
            f"disabled_users={self.disabled_users}"
            f")"
        )


@dataclass
class UpdateContext:
    """用户更新流程的上下文"""
    # 时间相关参数
    now_date: int = field(init=False)
    yesterday_date: int = field(init=False)
    current_timestamp: int = field(init=False)

    # 用户基本信息
    account_id: int
    access_token: str = field(init=False)
    user_stats: UserStats = field(init=False)
    user_record: UserRecord = field(init=False)

    # 用户数据库信息
    date_list: List[int] = field(
        init=False, default_factory=list
    )
    daily_summary: Dict[int, UserSummaryLocalEntry] = field(
        init=False, default_factory=dict
    )
    local_data: Dict[BattleMode, LocalDataEntry] = field(
        init=False, default_factory=dict
    )

    update_timestamp: int = field(init=False)
    update_plan: UpdatePlan = field(init=False)
    update_strategy: UpdateStrategy = field(
        init=False, default=UpdateStrategy.NORMAL
    )
    fetch_modes: Set[BattleMode] = field(
        init=False, default_factory=set
    )
    latest_data: Dict[BattleMode, LatestDataEntry] = field(
        init=False, default_factory=dict
    )

    def __post_init__(self) -> None:
        """初始化本轮更新时间参数"""
        self.update_plan = UpdatePlan()
        timestamp = TimeUtils.get_current_timestamp()

        self.current_timestamp = timestamp
        self.now_date = TimeUtils.get_reset_date(timestamp)
        self.yesterday_date = TimeUtils.get_reset_date(timestamp - 86400)

    @property
    def latest_summary(self) -> UserSummaryLocalEntry | None:
        """返回今日日期下的 daily_summary 记录"""
        return self.daily_summary.get(self.now_date)

    @property
    def dates_desc(self) -> list[int]:
        """返回从新到旧的日期列表，降序排列"""
        return sorted(self.date_list, reverse=True)

    @property
    def dates_asc(self) -> list[int]:
        """返回从旧到新的日期列表，升序排列"""
        return sorted(self.date_list)

    @property
    def query_interval(self) -> int | None:
        """距离上次查询的时间间隔，从未查询过则返回 None"""
        if self.user_record.last_query_at is None:
            return None
        return max(self.current_timestamp - self.user_record.last_query_at, 0)

    @property
    def battle_interval(self) -> int | None:
        """距离上次战斗的时间间隔，从未战斗过或隐藏战绩则返回 None"""
        if self.user_stats.last_battle_at is None:
            return None
        return max(self.current_timestamp - self.user_stats.last_battle_at, 0)

    @property
    def is_pro(self) -> bool:
        """用户是否需要计算详细近期数据"""
        if self.user_record.user_level != 2:
            return False

        latest_summary = self.daily_summary.get(self.now_date)
        if latest_summary is None:
            return False
        if latest_summary.updated_at is None:
            return False
        if self.current_timestamp - latest_summary.updated_at > 3600:
            return False

        return True
