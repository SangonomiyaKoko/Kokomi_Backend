from typing import TypedDict, List, Any
from dataclasses import dataclass, field

from .params import (
    ShipCacheParams, 
    ShipSnapshotParams, 
    DailyIndexParams,
    RecentStatsParams
)

class UpdateParams(TypedDict, total=False):
    insert: Any
    update: Any
    delete: Any

class CachePlan(TypedDict):
    insert: List[ShipCacheParams]
    update: List[ShipCacheParams]
    delete: List[ShipCacheParams]

class SnapshotPlan(TypedDict):
    insert: List[ShipSnapshotParams]
    update: List[ShipSnapshotParams]
    
class DailyIndexPlan(TypedDict):
    insert: DailyIndexParams
    update: DailyIndexParams

RecentPlan = list[RecentStatsParams]

@dataclass
class SnapshotUpdatePlan:
    """快照更新计划"""
    # 是否存在船只数据更改，若不存在更改则仅更新 user_daily_summary 表
    is_changed: bool = True
    
    # 用于更新 ship_latest_cache 表的 battles
    count: int = 0
    # 用于更新 user_daily_summary 和 ship_latest_cache 表的 index_table
    table: int = None

    # 用于更新 user_recent_stats 表的 Params
    recent: RecentPlan = field(default_factory=list)
    
    # 用于更新 ship_latest_cache 表的 Params
    cache: CachePlan = field(default_factory=lambda: {'insert': [], 'update': [],'delete': []})
    
    # 用于更新 daily_snapshot_index 表的 Params
    index: DailyIndexPlan = field(default_factory=lambda: {'insert': None, 'update': None})
    
    # 用于更新 ship_daily_snapshot 表的 Params
    snapshot: SnapshotPlan = field(default_factory=lambda: {'insert': [],'update': []})

    @property
    def cache_params(self) -> UpdateParams:
        """将 CachePlan 解析为可直接用于 SQL 操作的参数"""
        return {
            'insert': [params.as_insert_params() for params in self.cache['insert']],
            'update': [params.as_update_params() for params in self.cache['update']],
            'delete': [params.as_delete_params() for params in self.cache['delete']]
        }

    @property
    def index_params(self) -> UpdateParams:
        """将 DailyIndexPlan 解析为可直接用于 SQL 操作的参数"""
        return {
            'insert': self.index['insert'].as_insert_params() if self.index['insert'] else None,
            'update': self.index['update'].as_update_params() if self.index['update'] else None
        }

    @property
    def snapshot_params(self) -> UpdateParams:
        """将 SnapshotPlan 解析为可直接用于 SQL 操作的参数"""
        return {
            'insert': [params.as_insert_params() for params in self.snapshot['insert']],
            'update': [params.as_update_params() for params in self.snapshot['update']]
        }

    @property
    def recent_params(self) -> List[tuple]:
        """将 SnapshotPlan 解析为可直接用于 SQL 操作的参数"""
        return [params.as_insert_params() for params in self.recent]