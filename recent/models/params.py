from typing import Optional
from dataclasses import dataclass, field

from models import SingleShipData
from utils import StringUtils


@dataclass(frozen=True, slots=True)
class ShipCacheParams:
    """ship_latest_cache 参数对象"""
    ship_id: int
    battles: Optional[int] = None
    snapshot_date: Optional[int] = None
    
    def as_insert_params(self) -> tuple:
        """转换为 INSERT 语句的参数列表"""
        return (self.ship_id, self.battles, self.snapshot_date)
    
    def as_update_params(self) -> tuple:
        """转换为 UPDATE 语句的参数列表"""
        return (self.battles, self.snapshot_date, self.ship_id)
    
    def as_delete_params(self) -> tuple:
        """转换为 DELETE 语句的参数列表"""
        return (self.ship_id,)

@dataclass(frozen=True, slots=True)
class ShipSnapshotParams:
    """ship_latest_cache 参数对象"""
    ship_id: int
    snapshot_date: int
    snapshot_data: SingleShipData
    _encoded: str
    
    def __post_init__(self):
        object.__setattr__(self, '_encoded', StringUtils.ship_snapshot_encode(self.snapshot_data.to_list))
    
    def as_insert_params(self) -> tuple:
        """转换为 INSERT 语句的参数列表"""
        return (self.ship_id, self.snapshot_date, self._encoded)
    
    def as_update_params(self) -> tuple:
        """转换为 UPDATE 语句的参数列表"""
        return (self._encoded, self.ship_id, self.snapshot_date)

@dataclass(frozen=True, slots=True)
class DailyIndexParams:
    """daily_snapshot_index 参数对象"""
    snapshot_date: int
    ship_count: SingleShipData
    ship_map: dict
    _encoded: str
    
    def __post_init__(self):
        object.__setattr__(self, '_encoded', StringUtils.ship_map_encode(self.ship_map))
    
    def as_insert_params(self) -> tuple:
        """转换为 INSERT 语句的参数列表"""
        return (self.snapshot_date, self.ship_count, self._encoded)
    
    def as_update_params(self) -> tuple:
        """转换为 UPDATE 语句的参数列表"""
        return (self.ship_count, self._encoded, self.snapshot_date)

@dataclass(frozen=True, slots=True)
class RecentStatsParams:
    """user_recent_stats 参数对象"""
    ship_id: int
    mode: int
    battles: int
    wins: int
    losses: int
    damage: int
    frags: int
    original_exp: int
    scouting_damage: int
    art_agro: int
    planes_killed: int
    survived: int
    hit_rate: float
    
    def as_insert_params(self) -> tuple:
        """转换为 INSERT 语句的参数列表"""
        return (
            self.ship_id, self.mode, self.battles, self.wins,
            self.losses, self.damage, self.frags, self.original_exp,
            self.scouting_damage, self.art_agro, self.planes_killed,
            self.survived, self.hit_rate,
        )