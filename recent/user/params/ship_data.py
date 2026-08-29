from dataclasses import dataclass, field
from typing import List, Tuple, Any, Optional

from utils import StringUtils
from models import BattleMode, ShipDataEntry


@dataclass(frozen=True, slots=True)
class ShipDataUpdateEntry:
    ship_id: int
    ship_mode: int
    ship_index: int
    data_type_1: list = field(default_factory=list)
    data_type_2: list = field(default_factory=list)
    data_type_3: list = field(default_factory=list)

    def as_insert_params(self) -> tuple:
        """转换为数据库插入参数"""
        return (
            self.ship_id, self.ship_mode, self.ship_index,
            StringUtils.stats_encode(self.data_type_1),
            StringUtils.stats_encode(self.data_type_2),
            StringUtils.stats_encode(self.data_type_3)
        )


    def as_update_params(self) -> tuple:
        """转换为数据库更新参数"""
        return (
            StringUtils.stats_encode(self.data_type_1),
            StringUtils.stats_encode(self.data_type_2),
            StringUtils.stats_encode(self.data_type_3),
            self.ship_id, self.ship_mode, self.ship_index
        )


@dataclass
class ShipDataUpdateParams:
    insert: list[ShipDataUpdateEntry] = field(default_factory=list)
    update: list[ShipDataUpdateEntry] = field(default_factory=list)

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
        self, ship_id: int, ship_mode: BattleMode, ship_index: int, ship_data: Optional[ShipDataEntry]
    ) -> None:
        """添加一条船只数据更新参数"""
        if ship_data is None:
            ship_data = ShipDataEntry()

        self.update.append(
            ShipDataUpdateEntry(
                ship_id=ship_id,
                ship_mode=ship_mode.value,
                ship_index=ship_index,
                data_type_1=ship_data.solo.to_list() if ship_data.solo else None,
                data_type_2=ship_data.div2.to_list() if ship_data.div2 else None,
                data_type_3=ship_data.div3.to_list() if ship_data.div3 else None
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
        self, ship_id: int, ship_mode: BattleMode, ship_index: int, ship_data: Optional[ShipDataEntry]
    ) -> None:
        """添加一条船只数据插入参数"""
        if ship_data is None:
            ship_data = ShipDataEntry()

        self.insert.append(
            ShipDataUpdateEntry(
                ship_id=ship_id,
                ship_mode=ship_mode.value,
                ship_index=ship_index,
                data_type_1=ship_data.solo.to_list() if ship_data.solo else None,
                data_type_2=ship_data.div2.to_list() if ship_data.div2 else None,
                data_type_3=ship_data.div3.to_list() if ship_data.div3 else None
            )
        )
