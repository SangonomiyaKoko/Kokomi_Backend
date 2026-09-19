from typing import Dict, List, Set, Optional
from dataclasses import dataclass, field

from redis import Redis
from httpx import AsyncClient
from pymysql import Connection
from shard import TimeUtils, RedisKeys, ServicesName

from ..params import (
    UpdatePlan,
    LocalDataEntry,
    UserSummaryLocalEntry
)
from ..models import (
    BattleMode,
    UserStats,
    UserRecord,
    RunnerResult,
    UpdateStrategy,
    LatestDataEntry
)
from ..settings import (
    TIMEZONE,
    SEASON_CONFIG,
    REFRESH_INTERVAL
)


class RunCounter:
    """更新计数器"""

    def __init__(self):
        self.total = 0
        self.failed = 0
        self.skipped = 0
        self.updated = 0
        self.disabled = 0

    @property
    def failure_rate(self) -> int:
        """计算任务失败率"""
        if self.total == self.failed:
            return 100
        
        if self.total <= 20:
            # 样本过少，直接跳过
            return 0

    @property
    def metrics(self) -> str:
        """返回统计指标"""
        return (
            f"Total: {self.total}  "
            f"Updated: {self.updated}  "
            f"Skipped: {self.skipped}  "
            f"Disabled: {self.disabled}  "
            f"Failed: {self.failed}"
        )

    def incr(self) -> None:
        self.total += 1

    def record(self, result: RunnerResult) -> None:
        """记录更新结果对应的指标"""
        if result == RunnerResult.SKIPPED:
            self.skipped += 1
        elif result == RunnerResult.UPDATED:
            self.updated += 1
        elif result == RunnerResult.DISABLED:
            self.disabled += 1
        else:
            self.failed += 1


@dataclass
class RunContext:
    """整轮循环的上下文"""

    # 中间件客户端或者连接池
    redis_client: Redis = field(init=False)
    async_client: AsyncClient = field(init=False)
    mysql_connection: Connection = field(init=False)

    # 循环运行参数
    run_counter: RunCounter = field(init=False)
    
    clan_update_count: int = field(default=0)   # CLAN 模式已更新用户数
    key_expired_ts: int = field(init=False)     # 标记 Key 过期时间
    period_start_ts: int = field(init=False)    # CLAN 模式更新活跃时间段开启时间

    def __post_init__(self) -> None:
        self.run_counter = RunCounter()
        self.period_start_ts = TimeUtils.cb_update_period(
            tz=TIMEZONE,
            season_start=SEASON_CONFIG[0],
            season_finish=SEASON_CONFIG[1]
        )

    @property
    def failure_rate(self) -> int:
        """返回本次循环执行的任务失败率"""
        return self.run_counter.failure_rate

    def is_key_expiring(self) -> bool:
        """检查key有效期是否处于安全的区间内"""
        now_ts = TimeUtils.timestamp()
        return now_ts + 10 >= self.key_expired_ts

    def set_status_key(self) -> None:
        """刷新标识服务状态的键有效期"""
        status_key = RedisKeys.services(ServicesName.RECENT)
        self.redis_client.set(
            name=status_key,
            value=1,
            ex=REFRESH_INTERVAL + 10
        )
        self.key_expired_ts = TimeUtils.timestamp() + REFRESH_INTERVAL

    def del_status_key(self):
        """删除表示服务状态的键"""
        status_key = RedisKeys.services(ServicesName.RECENT)
        self.redis_client.delete(
            name=status_key
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
    latest_summary: Optional[UserSummaryLocalEntry] = field(init=False)
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
        timestamp = TimeUtils.timestamp()

        self.current_timestamp = timestamp
        self.now_date = TimeUtils.reset_date(TIMEZONE, timestamp)
        self.yesterday_date = TimeUtils.reset_date(TIMEZONE, timestamp - 86400)

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
