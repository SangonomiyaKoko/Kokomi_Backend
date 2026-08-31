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
    def from_api(cls, battle_stats: dict) -> ModeBattleStats:
        """从 API 数据创建 ModeBattleStats 对象"""
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

    def rates(self) -> Tuple[float, int, float, int]:
        """计算率值后的结果"""
        if self.battles <= 0:
            return 0.0, 0, 0.0, 0
        return (
            round(self.wins / self.battles * 100, 2),
            round(self.damage / self.battles),
            round(self.frags / self.battles, 2),
            round(self.exp / self.battles),
        )


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
    def from_api(cls, battle_stats: dict) -> ShipBattleStats:
        """从 VORTEX API 数据创建 ShipBattleStats 对象"""
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
    def from_api2(cls, battle_stats: dict) -> ShipBattleStats:
        """从 OFFICIAL API 数据创建 ShipBattleStats 对象"""
        total_exp = (
            battle_stats.get('wins', 0) * 2500
            + battle_stats.get('losses', 0) * 250
            + battle_stats.get('draws', 0) * 250
        )
        return cls(
            battles=battle_stats.get('battles', 0),
            wins=battle_stats.get('wins', 0),
            losses=battle_stats.get('losses', 0),
            damage=battle_stats.get('damage_dealt', 0),
            frags=battle_stats.get('frags', 0),
            survived=battle_stats.get('survived_battles', 0),
            scouting_damage=battle_stats.get('damage_scouting', 0),
            art_agro=battle_stats.get('art_agro', 0),
            original_exp=total_exp,
            planes_killed=battle_stats.get('planes_killed', 0),
            hits_by_main=battle_stats.get('main_battery', {}).get('hits', 0),
            shots_by_main=battle_stats.get('main_battery', {}).get('shots', 0)
        )

    @classmethod
    def from_row(cls, row: tuple) -> ShipBattleStats:
        """从数据库解码的数据创建 ShipBattleStats 对象"""
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
            self.original_exp,
            self.planes_killed,
            self.hits_by_main,
            self.shots_by_main,
        ]


@dataclass(slots=True)
class ShipDataEntry:
    """一条 (mode, ship) 的统计数据，对应 ship_index_data 一行"""
    solo: Optional[ShipBattleStats] = None    # data_type_1
    div2: Optional[ShipBattleStats] = None    # data_type_2
    div3: Optional[ShipBattleStats] = None    # data_type_3

    @property
    def battles(self) -> int:
        """该模式下该船的总战斗场次"""
        return sum(s.battles if s else 0 for s in (self.solo, self.div2, self.div3))

    def aggregate(self) -> ModeBattleStats:
        """汇总该船各数据类型的战绩为模式级统计"""
        parts = [s for s in (self.solo, self.div2, self.div3) if s is not None]
        if not parts:
            return ModeBattleStats(
                battles=0,
                wins=0,
                damage=0,
                frags=0,
                exp=0
            )
        else:
            return ModeBattleStats(
                battles=sum(p.battles for p in parts),
                wins=sum(p.wins for p in parts),
                damage=sum(p.damage for p in parts),
                frags=sum(p.frags for p in parts),
                exp=sum(p.original_exp for p in parts)
            )

    def set_type_stats(self, data_type: DataType, stats: ShipBattleStats) -> None:
        """写入指定数据类型的船只统计"""
        if data_type == DataType.SOLO:
            self.solo = stats
        elif data_type == DataType.DIV2:
            self.div2 = stats
        elif data_type == DataType.DIV3:
            self.div3 = stats
        else:
            raise ValueError(f'Unknown parameter {data_type}')

    def get_type_stats(self, data_type: DataType) -> Optional[ShipBattleStats]:
        """获取指定数据类型的船只统计"""
        if data_type == DataType.SOLO:
            return self.solo
        elif data_type == DataType.DIV2:
            return self.div2
        elif data_type == DataType.DIV3:
            return self.div3
        else:
            raise ValueError(f'Unknown parameter {data_type}')


@dataclass(slots=True)
class ShipDataCollection:
    """玩家所有船只数据的集合"""
    ships: Dict[int, ShipDataEntry] = field(default_factory=dict)

    @property
    def count(self) -> int:
        """返回船只数量"""
        return len(self.ships)

    def __iter__(self) -> Iterator[Tuple[int, ShipDataEntry]]:
        """返回迭代器，产生 (ship_id, ship_data) 元组"""
        return iter(self.ships.items())

    def setdefault(self, ship_id: int) -> None:
        """确保指定船只存在于集合中"""
        if ship_id not in self.ships:
            self.ships[ship_id] = ShipDataEntry()

    def is_exists(self, ship_id: int) -> bool:
        """判断指定船只是否存在"""
        return ship_id in self.ships

    def add_ship_data(self, ship_id: int, ship_data: ShipDataEntry) -> None:
        """添加或替换船只数据"""
        self.ships[ship_id] = ship_data

    def set_type_data(
        self, ship_id: int, data_type: DataType, stats: ShipBattleStats,
    ) -> None:
        """添加指定船只的数据类型统计"""
        self.ships[ship_id].set_type_stats(data_type, stats)

    def get_ship_data(self, ship_id: int) -> Optional[ShipDataEntry]:
        """获取指定船只的数据"""
        return self.ships.get(ship_id)

    def aggregate(self) -> ModeBattleStats:
        """汇总该船各数据类型的战绩"""
        total = [0] * 5
        for ship in self.ships.values():
            parts = [s for s in (ship.solo, ship.div2, ship.div3) if s is not None]
            if not parts:
                continue
            total[0] += sum(p.battles for p in parts)
            total[1] += sum(p.wins for p in parts)
            total[2] += sum(p.damage for p in parts)
            total[3] += sum(p.frags for p in parts)
            total[4] += sum(p.original_exp for p in parts)

        return ModeBattleStats(
            battles=total[0],
            wins=total[1],
            damage=total[2],
            frags=total[3],
            exp=total[4]
        )
