from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Any, Optional, Iterator

from models import BattleMode, ModeBattleStats


@dataclass(frozen=True, slots=True)
class ShipLatestLocalEntry:
    """本地数据库中记录的一艘船在一个模式下的索引数据"""
    battle: int
    index: Optional[int]


@dataclass(slots=True)
class ShipLatestLocalCollection:
    """一个模式下所有船只的索引数据合集"""
    entries: Dict[int, ShipLatestLocalEntry] = field(default_factory=dict)

    @property
    def count(self) -> int:
        """返回待处理记录数"""
        return len(self.entries)

    def __iter__(self) -> Iterator[Tuple[int, ShipLatestLocalEntry]]:
        """返回迭代器，产生 (ship_id, ship_data) 元组"""
        return iter(self.entries.items())

    def is_exists(self, ship_id: int) -> bool:
        """判断船只是否存在"""
        return ship_id in self.entries

    def get_entry(self, ship_id: int) -> Optional[ShipLatestLocalEntry]:
        """获取指定船只的本地记录"""
        return self.entries.get(ship_id)

    def set_ship_data(self, ship_id: int, battles: int, index: int) -> None:
        """设置指定船只的本地记录"""
        self.entries[ship_id] = ShipLatestLocalEntry(battle=battles, index=index)


@dataclass(frozen=True, slots=True)
class ShipLatestUpdateEntry:
    ship_id: int
    ship_mode: int
    battles: int = 0
    win_rate: float = 0.0
    avg_damage: int = 0
    avg_frags: float = 0.0
    avg_exp: int = 0
    data_index: Optional[int] = None

    def as_insert_params(self) -> tuple:
        """转换为数据库插入参数"""
        return (
            self.ship_id, self.ship_mode, self.battles, self.win_rate,
            self.avg_damage, self.avg_frags, self.avg_exp, self.data_index
        )

    def as_update_params(self) -> tuple:
        """转换为数据库更新参数"""
        return (
            self.battles, self.win_rate, self.avg_damage, self.avg_frags,
            self.avg_exp, self.data_index, self.ship_id, self.ship_mode
        )


@dataclass
class ShipLatestUpdateParams:
    insert: list[ShipLatestUpdateEntry] = field(default_factory=list)
    update: list[ShipLatestUpdateEntry] = field(default_factory=list)

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
        self, ship_id: int, ship_mode: BattleMode, ship_data: ModeBattleStats | None, ship_index: int
    ) -> None:
        """添加一条船只概览更新参数"""
        if not ship_data:
            ship_data = ModeBattleStats(0,0,0,0,0)

        ship_rates_data = ship_data.rates()
        self.update.append(
            ShipLatestUpdateEntry(
                ship_id=ship_id,
                ship_mode=ship_mode.value,
                battles=ship_data.battles,
                win_rate=ship_rates_data[0],
                avg_damage=ship_rates_data[1],
                avg_frags=ship_rates_data[2],
                avg_exp=ship_rates_data[3],
                data_index=ship_index
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
        self, ship_id: int, ship_mode: BattleMode, ship_data: ModeBattleStats | None, ship_index: int
    ) -> None:
        """添加一条船只概览插入参数"""
        if not ship_data:
            ship_data = ModeBattleStats(0,0,0,0,0)

        ship_rates_data = ship_data.rates()
        self.insert.append(
            ShipLatestUpdateEntry(
                ship_id=ship_id,
                ship_mode=ship_mode.value,
                battles=ship_data.battles,
                win_rate=ship_rates_data[0],
                avg_damage=ship_rates_data[1],
                avg_frags=ship_rates_data[2],
                avg_exp=ship_rates_data[3],
                data_index=ship_index
            )
        )
