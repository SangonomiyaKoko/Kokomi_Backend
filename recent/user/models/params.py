from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from utils import StringUtils

from .mode import BattleMode
from .ship_data import ShipData


@dataclass(frozen=True, slots=True)
class ShipLatestIndexParams:
    """ship_latest_index 行参数（全行状态，跨模式合并后使用）"""
    ship_id: int
    pvp_battles: int = 0
    rank_battles: int = 0
    clan_battles: int = 0
    pvp_index: Optional[int] = None
    rank_index: Optional[int] = None
    clan_index: Optional[int] = None

    def as_insert_params(self) -> tuple:
        return (
            self.ship_id, self.pvp_battles, self.rank_battles,
            self.clan_battles, self.pvp_index, self.rank_index, self.clan_index
        )

    def as_update_params(self) -> tuple:
        return (
            self.pvp_battles, self.rank_battles, self.clan_battles,
            self.pvp_index, self.rank_index, self.clan_index, self.ship_id
        )

    def as_delete_params(self) -> tuple:
        return (self.ship_id,)


@dataclass(frozen=True, slots=True)
class ShipIndexDataParams:
    """ship_index_data 行参数"""
    ship_id: int
    ship_mode: int
    ship_index: int
    data_type_1: Optional[str] = None
    data_type_2: Optional[str] = None
    data_type_3: Optional[str] = None

    @classmethod
    def from_ship_data(
        cls, ship_id: int, mode: BattleMode, ship_index: int, ship_data: ShipData
    ) -> ShipIndexDataParams:
        """从船只数据构造参数（序列化各数据类型）"""
        return cls(
            ship_id=ship_id,
            ship_mode=mode.value,
            ship_index=ship_index,
            data_type_1=StringUtils.stats_encode(ship_data.solo.to_list()) if ship_data.solo else None,
            data_type_2=StringUtils.stats_encode(ship_data.div2.to_list()) if ship_data.div2 else None,
            data_type_3=StringUtils.stats_encode(ship_data.div3.to_list()) if ship_data.div3 else None,
        )

    def as_insert_params(self) -> tuple:
        return (
            self.ship_id, self.ship_mode, self.ship_index,
            self.data_type_1, self.data_type_2, self.data_type_3
        )

    def as_update_params(self) -> tuple:
        return (
            self.data_type_1, self.data_type_2, self.data_type_3,
            self.ship_id, self.ship_mode, self.ship_index
        )


@dataclass(frozen=True, slots=True)
class ShipIndexMapParams:
    """ship_index_map 行参数"""
    ship_mode: int
    ship_index: int
    ships: int
    battles: int
    wins: int
    damage: int
    frags: int
    exp: int
    index_map: str

    def as_insert_params(self) -> tuple:
        return (
            self.ship_mode, self.ship_index, self.ships, self.battles,
            self.wins, self.damage, self.frags, self.exp, self.index_map
        )

    def as_update_params(self) -> tuple:
        return (
            self.ships, self.battles, self.wins, self.damage,
            self.frags, self.exp, self.index_map, self.ship_mode, self.ship_index
        )


@dataclass(frozen=True, slots=True)
class RecentStatsParams:
    """user_recent_stats 行参数"""
    ship_id: int
    data_mode: int
    data_type: int
    battles: int
    wins: int
    losses: int
    exp: int
    damage: int
    planes: int
    frags: int
    survived: int
    scout_damage: int
    art_agro: int
    hit_rate: float
    battle_time: int

    def as_insert_params(self) -> tuple:
        return (
            self.ship_id, self.data_mode, self.data_type, self.battles,
            self.wins, self.losses, self.exp, self.damage, self.planes,
            self.frags, self.survived, self.scout_damage, self.art_agro,
            self.hit_rate, self.battle_time
        )
