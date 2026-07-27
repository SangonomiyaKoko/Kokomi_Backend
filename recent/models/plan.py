from typing import TypedDict, List
from dataclasses import dataclass, field

from .params import (
    ShipCacheParams, 
    ShipSnapshotParams, 
    DailyIndexParams,
    RecentStatsParams
)


class CachePlan(TypedDict):
    insert: List[ShipCacheParams]
    update: List[ShipCacheParams]
    delete: List[ShipCacheParams]

class SnapshotPlan(TypedDict):
    insert: List[ShipSnapshotParams]
    update: List[ShipSnapshotParams]
    
class DailyIndexPlan(TypedDict):
    insert: List[DailyIndexParams]
    update: List[DailyIndexParams]

RecentPlan = list[RecentStatsParams]

@dataclass
class SnapshotUpdatePlan:
    """快照更新计划"""
    count: int = 0
    table: int = None
    is_changed: bool = True
    recent: RecentPlan = []
    cache: CachePlan = field(default_factory=lambda: {'insert': [], 'update': [],'delete': []})
    index: DailyIndexPlan = field(default_factory=lambda: {'insert': [],'update': []})
    snapshot: SnapshotPlan = field(default_factory=lambda: {'insert': [],'update': []})