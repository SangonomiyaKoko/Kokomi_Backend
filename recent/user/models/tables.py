from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .mode import BattleMode, FULL_UPDATE_MODES

# 特殊行 ID：用于 ship_latest_index 记录各模式最新字段（summary 异常时的兜底来源）
SPECIAL_SHIP_ID_FOR_INDEX = 1_000_000_000


@dataclass(frozen=True, slots=True)
class DailySummary:
    """user_daily_summary 表的一行数据"""
    is_public: bool
    total_battles: int
    pve_battles: int
    pvp_battles: int
    rank_battles: int
    clan_battles: int
    karma: int
    pvp_index: Optional[int]
    rank_index: Optional[int]
    clan_index: Optional[int]
    updated_at: int

    def get_index(self, mode: BattleMode) -> Optional[int]:
        """获取指定模式的统计索引（NULL=未记录 0=无数据 日期=有数据）"""
        if mode == BattleMode.PVP:
            return self.pvp_index
        if mode == BattleMode.RANK:
            return self.rank_index
        if mode == BattleMode.CLAN:
            return self.clan_index

    def to_row(self, no_clan_stats: bool = False) -> list:
        """转为数据库插入/更新用的 list"""
        if no_clan_stats:
            return [
                self.is_public, self.total_battles, self.pve_battles,
                self.pvp_battles, self.rank_battles, self.karma, 
                self.pvp_index, self.rank_index, self.updated_at
            ]
        else:
            return [
                self.is_public, self.total_battles, self.pve_battles,
                self.pvp_battles, self.rank_battles, self.clan_battles,
                self.karma, self.pvp_index, self.rank_index, self.clan_index,
                self.updated_at
            ]

    @classmethod
    def from_row(cls, row: tuple) -> DailySummary:
        """从数据库查询结果 tuple 构造实例"""
        return cls(
            is_public=bool(row[0]),
            total_battles=row[1],
            pve_battles=row[2],
            pvp_battles=row[3],
            rank_battles=row[4],
            clan_battles=row[5],
            karma=row[6],
            pvp_index=row[7],
            rank_index=row[8],
            clan_index=row[9],
            updated_at=row[10]
        )


@dataclass(frozen=True, slots=True)
class ShipCacheEntry:
    """ship_latest_index 中一艘船的数据（按模式存战斗场次与索引）"""
    battles: Dict[BattleMode, Optional[int]]
    indexs: Dict[BattleMode, Optional[int]]

    def get_battle(self, mode: BattleMode) -> int:
        """获取指定模式的总场次缓存"""
        return self.battles.get(mode)

    def get_index(self, mode: BattleMode) -> Optional[int]:
        """获取指定模式的 map 索引"""
        return self.indexs.get(mode)


@dataclass(slots=True)
class ShipCache:
    """ship_latest_index 表的缓存数据（含特殊行）"""
    # 特殊行：各模式最新战斗场次与索引（模式变更检测的比对基准）
    battles: Dict[BattleMode, Optional[int]] = field(default_factory=dict)
    indexs: Dict[BattleMode, Optional[int]] = field(default_factory=dict)

    entries: Dict[int, ShipCacheEntry] = field(default_factory=dict)

    @property
    def is_new_user(self) -> bool:
        """判定是否存在本地缓存数据，即所有模式的索引均为 None"""
        for mode in FULL_UPDATE_MODES:
            if not (self.indexs.get(mode) is None):
                return False
        return True

    @property
    def ship_ids(self) -> List[int]:
        return list(self.entries.keys())

    def is_exists(self, ship_id: int) -> bool:
        return ship_id in self.entries

    def get_entry(self, ship_id: int) -> Optional[ShipCacheEntry]:
        return self.entries.get(ship_id)

    def get_battle(self, mode: BattleMode) -> int:
        """获取指定模式的总场次缓存"""
        return self.battles.get(mode)

    def get_index(self, mode: BattleMode) -> Optional[int]:
        """获取指定模式的 map 索引"""
        return self.indexs.get(mode)

    @classmethod
    def from_rows(cls, rows: tuple) -> ShipCache:
        """从数据库加载全部数据（含特殊行）"""
        cache = cls()
        for row in rows:
            ship_id, pvp, rank, clan, pvp_idx, rank_idx, clan_idx = row
            row_battles = {
                BattleMode.PVP: pvp,
                BattleMode.RANK: rank,
                BattleMode.CLAN: clan
            }
            row_indexs = {
                BattleMode.PVP: pvp_idx,
                BattleMode.RANK: rank_idx,
                BattleMode.CLAN: clan_idx
            }
            if ship_id == SPECIAL_SHIP_ID_FOR_INDEX:
                cache.battles = row_battles
                cache.indexs = row_indexs
            else:
                cache.entries[ship_id] = ShipCacheEntry(battles=row_battles,indexs=row_indexs)
        return cache
