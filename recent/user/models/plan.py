from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, TypedDict

from .mode import BattleMode
from .params import RecentStatsParams


class UpdateParams(TypedDict, total=False):
    insert: Any
    update: Any
    delete: Any


@dataclass
class ModePlan:
    """单个模式的更新计划（只包含该模式独立的写入）"""
    mode: BattleMode
    is_changed: bool
    map_index: Optional[int] = None                     # 本模式本次采用的 map 索引（供 summary 写入）
    map_params: Optional[UpdateParams] = None          # ship_index_map 的 insert/update
    data_params: Optional[UpdateParams] = None         # ship_index_data 的 insert/update
    cache_changes: Dict[int, tuple] = field(default_factory=dict)  # ship_id → (battles, index)，供跨模式合并
    recent: List[RecentStatsParams] = field(default_factory=list)


@dataclass
class SnapshotUpdatePlan:
    """整体更新计划：按模式拆分 + 合并后的船只缓存写入"""
    modes: Dict[BattleMode, ModePlan] = field(default_factory=dict)
    cache_params: UpdateParams = field(
        default_factory=lambda: {'insert': [], 'update': [], 'delete': []}
    )

    @property
    def is_changed(self) -> bool:
        return any(plan.is_changed for plan in self.modes.values())

    def mode(self, mode: BattleMode) -> Optional[ModePlan]:
        return self.modes.get(mode)

    @property
    def recent_params(self) -> List[tuple]:
        """将所有模式的 recent 差值解析为 SQL 插入参数"""
        return [
            params.as_insert_params()
            for mode_plan in self.modes.values()
            for params in mode_plan.recent
        ]
