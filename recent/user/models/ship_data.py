from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterator, List, Optional, Tuple

from .mode import DataType

@dataclass(frozen=True, slots=True)
class ModeBattleStats:
    """某个模式下简略统计数据"""
    battles: int
    wins: int
    damage: int
    frags: int
    exp: int

    @classmethod
    def from_api_data(cls, battle_stats: dict) -> ModeBattleStats:
        """从API数据创建ModeBattleStats对象"""
        return cls(
            battles=battle_stats.get('battles_count', 0),
            wins=battle_stats.get('wins', 0),
            damage=battle_stats.get('damage_dealt', 0),
            frags=battle_stats.get('frags', 0),
            exp=battle_stats.get('original_exp', 0)
        )

    def to_list(self) -> List[int]:
        """转换为列表格式，用于序列化"""
        return [self.battles, self.wins, self.damage, self.frags, self.exp]


@dataclass(frozen=True, slots=True)
class ShipBattleStats:
    """某个模式下单条船只的统计数据"""
    battles: int
    wins: int
    losses: int
    damage: int
    frags: int
    survived: int
    scouting_damage: int
    art_agro: int
    original_exp: int
    planes_killed: int
    hits_by_main: int
    shots_by_main: int

    @classmethod
    def from_api_data(cls, battle_stats: dict) -> ShipBattleStats:
        """从API数据创建ShipBattleStats对象"""
        return cls(
            battles=battle_stats.get('battles_count', 0),
            wins=battle_stats.get('wins', 0),
            losses=battle_stats.get('losses', 0),
            damage=battle_stats.get('damage_dealt', 0),
            frags=battle_stats.get('frags', 0),
            survived=battle_stats.get('survived', 0),
            scouting_damage=max(
                battle_stats.get('assist_damage', 0),
                battle_stats.get('scouting_damage', 0),
            ),
            art_agro=battle_stats.get('art_agro', 0),
            original_exp=battle_stats.get('original_exp', 0),
            planes_killed=battle_stats.get('planes_killed', 0),
            hits_by_main=battle_stats.get('hits_by_main', 0),
            shots_by_main=battle_stats.get('shots_by_main', 0)
        )

    @classmethod
    def from_row(cls, row: tuple) -> ShipBattleStats:
        """从数据库解码的数据创建ShipBattleStats对象"""
        return cls(
            battles=row[0],
            wins=row[1],
            losses=row[2],
            damage=row[3],
            frags=row[4],
            survived=row[5],
            scouting_damage=row[6],
            art_agro=row[7],
            original_exp=row[8],
            planes_killed=row[9],
            hits_by_main=row[10],
            shots_by_main=row[11]
        )

    def to_list(self) -> List[int]:
        """转换为列表格式，用于序列化"""
        return [
            self.battles, self.wins, self.losses, self.damage,
            self.frags, self.survived, self.scouting_damage, self.art_agro,
            self.original_exp, self.planes_killed, self.hits_by_main, self.shots_by_main,
        ]


@dataclass(slots=True)
class ShipData:
    """一个 (mode, ship) 的统计数据，对应 ship_index_data 一行"""
    solo: Optional[ShipBattleStats] = None    # data_type_1
    div2: Optional[ShipBattleStats] = None    # data_type_2（clan 模式为 div）
    div3: Optional[ShipBattleStats] = None    # data_type_3

    @property
    def battles(self) -> int:
        """该模式下该船的总战斗场次"""
        return sum(s.battles if s else 0 for s in (self.solo, self.div2, self.div3))

    def set_type_stats(self, data_type: DataType, stats: ShipBattleStats) -> None:
        if data_type == DataType.SOLO:
            self.solo = stats
        elif data_type == DataType.DIV2:
            self.div2 = stats
        else:
            self.div3 = stats

    def get_type_stats(self, data_type: DataType) -> Optional[ShipBattleStats]:
        if data_type == DataType.SOLO:
            return self.solo
        if data_type == DataType.DIV2:
            return self.div2
        return self.div3

@dataclass(slots=True)
class ShipDataCollection:
    """玩家所有船只数据的集合"""
    ships: Dict[int, ShipData] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.ships)

    @property
    def ship_ids(self) -> List[int]:
        return list(self.ships.keys())

    def __iter__(self) -> Iterator[Tuple[int, ShipData]]:
        """返回迭代器，产生 (ship_id, ship_data) 元组"""
        return iter(self.ships.items())

    def setdefault(self, ship_id: int):
        if ship_id not in self.ships:
            self.ships[ship_id] = ShipData()

    def is_exists(self, ship_id: int) -> bool:
        return ship_id in self.ships

    def add_ship_data(self, ship_id: int, ship_data: ShipData) -> None:
        self.ships[ship_id] = ship_data

    def add_type_data(self, ship_id: int, data_type: DataType, stats: ShipBattleStats) -> None:
        self.ships[ship_id].set_type_stats(data_type, stats)

    def get_ship_data(self, ship_id: int) -> Optional[ShipData]:
        return self.ships.get(ship_id)
