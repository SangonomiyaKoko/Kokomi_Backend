from dataclasses import dataclass, field
from typing import List, Tuple, Any, Optional

from utils import StringUtils
from models import BattleMode, ModeBattleStats


@dataclass(frozen=True, slots=True)
class ShipMapUpdateEntry:
    ship_mode: int
    ship_index: int
    ships: int = 0
    battles: int = 0
    wins: int = 0
    damage: int = 0
    frags: int = 0
    exp: int = 0
    index_map: dict = field(default_factory=dict)
    update_time: Optional[int] = None

    def as_insert_params(self) -> tuple:
        """转换为数据库插入参数"""
        return (
            self.ship_mode, self.ship_index, self.ships, self.battles,
            self.wins, self.damage, self.frags, self.exp,
            StringUtils.index_map_encode(self.index_map), self.update_time
        )

    def as_update_params(self) -> tuple:
        """转换为数据库更新参数"""
        return (
            self.ships, self.battles, self.wins, self.damage,
            self.frags, self.exp, StringUtils.index_map_encode(self.index_map),
            self.update_time, self.ship_mode, self.ship_index
        )


@dataclass
class ShipMapUpdateParams:
    insert: list[ShipMapUpdateEntry] = field(default_factory=list)
    update: list[ShipMapUpdateEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        """返回待处理记录数"""
        return len(self.insert) + len(self.update)

    @property
    def has_params(self) -> bool:
        """判断是否没有待处理参数"""
        return len(self.insert) == 0 and len(self.update) == 0

    @property
    def has_update_params(self) -> bool:
        """判断是否存在更新参数"""
        return len(self.update) > 0

    @property
    def get_update_params(self) -> List[Tuple[Any]]:
        """返回数据库更新参数列表"""
        return [p.as_update_params() for p in self.update]

    def set_update_params(
        self, ship_mode: BattleMode, ship_index: int, ship_map: dict, ship_data: Optional[ModeBattleStats], updated_at: int
    ) -> None:
        """添加一条模式映射更新参数"""
        if ship_data is None:
            ship_data = ModeBattleStats.from_api({})

        ship_count = len(ship_map)
        ship_data_list = ship_data.to_list()
        self.update.append(
            ShipMapUpdateEntry(
                ship_mode=ship_mode.value,
                ship_index=ship_index,
                ships=ship_count,
                battles=ship_data_list[0],
                wins=ship_data_list[1],
                damage=ship_data_list[2],
                frags=ship_data_list[3],
                exp=ship_data_list[4],
                index_map=ship_map,
                update_time=updated_at

            )
        )

    @property
    def has_insert_params(self) -> bool:
        """判断是否存在插入参数"""
        return len(self.insert) > 0

    @property
    def get_insert_params(self) -> List[Tuple[Any]]:
        """返回数据库插入参数列表"""
        return [p.as_insert_params() for p in self.insert]

    def set_insert_params(
        self, ship_mode: BattleMode, ship_index: int, ship_map: dict, ship_data: Optional[ModeBattleStats], updated_at: int
    ) -> None:
        """添加一条模式映射插入参数"""
        if ship_data is None:
            ship_data = ModeBattleStats.from_api({})

        ship_count = len(ship_map)
        ship_data_list = ship_data.to_list()
        self.insert.append(
            ShipMapUpdateEntry(
                ship_mode=ship_mode.value,
                ship_index=ship_index,
                ships=ship_count,
                battles=ship_data_list[0],
                wins=ship_data_list[1],
                damage=ship_data_list[2],
                frags=ship_data_list[3],
                exp=ship_data_list[4],
                index_map=ship_map,
                update_time=updated_at

            )
        )
