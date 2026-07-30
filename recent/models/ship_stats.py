from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Iterator, Tuple


class BattleMode(Enum):
    """战斗模式枚举"""
    PVP_SOLO = "pvp_solo"
    PVP_DIV2 = "pvp_div2"
    PVP_DIV3 = "pvp_div3"
    RANK_SOLO = "rank_solo"
    
    @classmethod
    def list_modes(cls) -> List[str]:
        return [mode.value for mode in cls]

@dataclass(frozen=True, slots=True)
class ShipBattleStats:
    """单条船只的统计数据"""
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
        """从SQLite3数据库数据创建ShipBattleStats对象"""
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
        """转换为列表格式，保持与原代码兼容"""
        return [
            self.battles,
            self.wins,
            self.losses,
            self.damage,
            self.frags,
            self.survived,
            self.scouting_damage,
            self.art_agro,
            self.original_exp,
            self.planes_killed,
            self.hits_by_main,
            self.shots_by_main,
        ]

@dataclass(slots=True)
class SingleShipData:
    """单艘船只的完整数据"""
    ship_id: int
    stats: List[Optional[ShipBattleStats]] = field(default_factory=lambda: [None] * 4)

    @property
    def battles(self):
        return sum(i.battles if i else 0 for i in self.stats)

    @property
    def to_list(self):
        return [stat.to_list() if stat is not None else None for stat in self.stats]
    
    def set_mode_stats(self, mode_index: int, stats: ShipBattleStats):
        """设置指定模式的统计数据"""
        if not 0 <= mode_index < 4:
            raise ValueError("mode_index must be between 0 and 3")
        self.stats[mode_index] = stats
    
    def get_mode_stats(self, mode_index: int) -> Optional[ShipBattleStats]:
        """获取指定模式的统计数据"""
        if not 0 <= mode_index < 4:
            raise ValueError("mode_index must be between 0 and 3")
        return self.stats[mode_index]

@dataclass(slots=True)
class ShipDataCollection:
    """玩家所有船只数据的集合"""
    ships: Dict[int, SingleShipData] = field(default_factory=dict)

    @property
    def count(self):
        return len(self.ships)
    
    def __iter__(self) -> Iterator[Tuple[int, SingleShipData]]:
        """返回迭代器，产生 (ship_id, ship_data) 元组"""
        return iter(self.ships.items())

    def is_exists(self, ship_id: int):
        return ship_id in self.ships
    
    def add_ship_data(self, ship_id: int, ship_data: SingleShipData):
        """添加或更新船只数据"""
        self.ships[ship_id] = ship_data
    
    def get_ship_data(self, ship_id: int) -> Optional[SingleShipData]:
        """获取指定船只的数据"""
        return self.ships.get(ship_id)
    
    @classmethod
    def from_responses(cls,account_id: int, responses: List[Dict]) -> ShipDataCollection:
        """从API响应创建ShipDataCollection对象"""
        collection = cls()
        modes = BattleMode.list_modes()
        
        for mode_index, response in enumerate(responses):
            mode = modes[mode_index]
            mode_data = response[str(account_id)]['statistics']
            for ship_id_str, ship_data in mode_data.items():
                ship_id = int(ship_id_str)
                
                # 获取该船只的统计数据
                battle_stats = ship_data.get(mode, {})
                if (
                    not battle_stats or 
                    battle_stats.get('battles_count', 0) == 0
                ):
                    continue
                
                # 创建或获取ShipData对象
                if ship_id not in collection.ships:
                    collection.ships[ship_id] = SingleShipData(ship_id)
                
                # 设置对应模式的统计数据
                stats_obj = ShipBattleStats.from_api_data(battle_stats)
                collection.ships[ship_id].set_mode_stats(mode_index, stats_obj)
        
        return collection