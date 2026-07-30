from __future__ import annotations

from redis import Redis
from httpx import AsyncClient
from pymysql import Connection
from dataclasses import dataclass, field

from utils import TimeUtils

from .tables import DailySummary, ShipCache
from .ship_stats import ShipDataCollection
from .user import UserRecord, UserStats


@dataclass
class UpdateContext:
    """用户更新流程的上下文"""
    redis_client: Redis
    async_client: AsyncClient
    mysql_connection: Connection

    # 当前时间戳
    current_timestamp: int
    now_date: int = field(init=False)
    yesterday_date: int = field(init=False)

    # 用户基本信息
    account_id: int
    user_stats: UserStats = field(init=False)
    user_record: UserRecord = field(init=False)

    # 用户数据库信息
    date_list: list[int] = field(init=False)
    daily_summary: dict[int, DailySummary] = field(init=False)
    ship_cache: ShipCache = field(init=False)

    # 数据接口请求结果
    ship_data: ShipDataCollection = field(init=False)

    def __post_init__(self) -> None:
        self.now_date = TimeUtils.get_reset_date(self.current_timestamp)
        self.yesterday_date = TimeUtils.get_reset_date(self.current_timestamp - 86400)

    @property
    def has_any_summary(self) -> bool:
        """是否已有任何 daily_summary 数据"""
        return len(self.daily_summary) > 0

    @property
    def latest_summary(self) -> DailySummary | None:
        """返回今日日期下的 daily_summary 记录"""
        return self.daily_summary.get(self.now_date)
    
    @property
    def dates_desc(self) -> list[int]:
        """返回从新到旧（降序）的日期列表"""
        return sorted(self.date_list, reverse=True)
    
    @property
    def dates_asc(self) -> list[int]:
        """返回从旧到新（升序）的日期列表"""
        return sorted(self.date_list)
    
    @property
    def query_interval(self) -> int | None:
        """距离上次查询的时间间隔，如果从未查询过则返回None"""
        if self.user_record.last_query_at is None:
            return None
        return max(self.current_timestamp - self.user_record.last_query_at, 0)

    @property
    def battle_interval(self) -> int | None:
        """距离上次战斗的时间间隔，如果从未战斗过或隐藏战绩则返回None"""
        if self.user_stats.last_battle_at is None:
            return None
        return max(self.current_timestamp - self.user_stats.last_battle_at, 0)

    @property
    def is_pro(self) -> bool:
        """用户是否需要计算详细近期数据"""
        if not self.user_record.user_level == 2:
            return False
        latest_summary = self.daily_summary.get(self.now_date)
        if latest_summary is None:
            return False
        if latest_summary.updated_at is None:
            return False
        if self.current_timestamp - latest_summary.updated_at > 3600:
            return False
        return True

    def __str__(self) -> str:
        # 获取原始字符串表示
        s = super().__str__()
        
        # 替换这三个字段的显示
        replacements = {
            f"redis_client={self.redis_client}": f"redis_client={hex(id(self.redis_client))}",
            f"async_client={self.async_client}": f"async_client={hex(id(self.async_client))}",
            f"mysql_connection={self.mysql_connection}": f"mysql_connection={hex(id(self.mysql_connection))}",
        }
        
        for old, new in replacements.items():
            s = s.replace(old, new)
        
        return s