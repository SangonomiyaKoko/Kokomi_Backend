from __future__ import annotations

from typing import NamedTuple
from dataclasses import dataclass, field

from .ship_stats import SingleShipData


SPECIAL_SHIP_ID_FOR_INDEX = 1_000_000_000

@dataclass(frozen=True, slots=True)
class DailySummary:
    """user_daily_summary 表的一行数据"""
    is_public: bool
    total_battles: int
    pve_battles: int
    pvp_battles: int
    ranked_battles: int
    karma: int
    index_table: str | None
    updated_at: int

    def to_row(self) -> list:
        """转为数据库插入/更新用的 list"""
        return [
            self.is_public,
            self.total_battles,
            self.pve_battles,
            self.pvp_battles,
            self.ranked_battles,
            self.karma,
            self.index_table,
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
            ranked_battles=row[4],
            karma=row[5],
            index_table=row[6],
            updated_at=row[7]
        )

    def __str__(self) -> str:
        """输出字符串"""
        return (
            f"DailySummary("
            f"is_public={self.is_public}, "
            f"total_battles={self.total_battles}, "
            f"pvp_battles={self.pvp_battles}, "
            f"ranked_battles={self.ranked_battles}, "
            f"karma={self.karma}, "
            f"index_table={self.index_table}, "
            f"updated_at={self.updated_at}"
            f")"
        )

class ShipCacheTuple(NamedTuple):
    """ship_latest_cache 的数据结构"""
    battles_count: int
    snapshot_date: int

    def is_battle_unchanged(self, battles: int) -> bool:
        """判断战斗场次是否与缓存一致"""
        return battles == self.battles_count

    def __str__(self) -> str:
        return f"ShipCacheTuple(battles={self.battles_count}, date={self.snapshot_date})"

@dataclass(frozen=True, slots=True)
class ShipCache:
    """ship_latest_cache 表的缓存数据"""
    date: int | None
    data: dict[int, ShipCacheTuple] = field(default_factory=dict)

    def is_exists(self, ship_id: int) -> bool:
        return ship_id in self.data

    def is_stats_unchanged(self, ship_data: SingleShipData) -> bool:
        """检测船只数据和缓存相比是否存在变动（True = 无变动）"""
        ship_cache = self.data.get(ship_data.ship_id)
        if ship_cache is None:
            return False
        return ship_cache.is_battle_unchanged(ship_data.battles)

    def is_date_unchanged(self, ship_id: int, now_date: int) -> bool:
        """检测船只缓存数据中的 snapshot_date 是否等于 now_date"""
        return self.data.get(ship_id).snapshot_date == now_date
    
    def get_ship_ids(self) -> list[int]:
        """获取缓存中船只 ID 列表"""
        if self.data:
            return list(self.data.keys())
        return []

    def get_ship_tuple(self, ship_id: int) -> tuple[int, int]:
        """获取缓存中指定船只 snapshot_date 数据"""
        ship_data = self.data.get(ship_id)
        if ship_data is None:
            return None, None
        return ship_data.battles_count, ship_data.snapshot_date

    @classmethod
    def from_rows(cls, rows: tuple[tuple]) -> ShipCache:
        """从数据库加载全部数据"""
        date = None
        data = {}
        for ship_id, battles, snapshot_date in rows:
            # 在数据表中通过特殊 ID 来储存 ship_cache 对应的 index_table
            if ship_id == SPECIAL_SHIP_ID_FOR_INDEX:
                if snapshot_date != 0:
                    date = snapshot_date
            else:
                data[ship_id] = ShipCacheTuple(battles, snapshot_date)
        return cls(date=date, data=data)

    def __str__(self) -> str:
        return f"ShipCache(date={self._date}, size={len(self._data)})"