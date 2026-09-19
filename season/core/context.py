from dataclasses import dataclass, field
from typing import Dict, List, Optional

from redis import Redis
from requests import Session
from pymysql import Connection
from shard import RedisKeys, ServicesName

from ..models import (
    BattleRecord,
    LeagueClanEntry,
    ClanSeasonStats,
    ClanTeamCache
)
from ..settings import REFRESH_INTERVAL


@dataclass
class RunContext:
    """整轮循环的上下文"""

    # 中间件客户端或者连接池
    session: Session = field(init=False)
    redis_client: Redis = field(init=False)
    mysql_connection: Connection = field(init=False)

    # 本赛季信息
    season_id: int = field(default=0)
    clan_entries: List[LeagueClanEntry] = field(
        default_factory=list
    )
    league_counts: Dict[str, int] = field(
        default_factory=dict
    )

    # 本次更新统计到赛季对局数量
    record_match = 0
    discard_match = 0

    def set_status_key(self) -> None:
        """刷新标识服务状态的键有效期"""
        status_key = RedisKeys.services(ServicesName.SEASON)
        self.redis_client.set(
            name=status_key,
            value=1,
            ex=REFRESH_INTERVAL + 100
        )

    def del_status_key(self) -> None:
        """删除表示服务状态的键"""
        status_key = RedisKeys.services(ServicesName.SEASON)
        self.redis_client.delete(status_key)


@dataclass
class UpdateContext:
    """单个公会更新流程的上下文"""
    clan_id: int
    season_id: int

    record: BattleRecord = field(init=False, default=None)
    stats: ClanSeasonStats = field(init=False, default=None)
    cache: Optional[ClanTeamCache] = field(init=False, default=None)
