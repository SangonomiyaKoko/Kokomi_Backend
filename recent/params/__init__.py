from dataclasses import dataclass

from .ship_map import ShipMapUpdateParams
from .ship_data import ShipDataUpdateParams
from .mode_latest import ModeLatestUpdateParams, ModeLatestLocalEntry
from .ship_latest import ShipLatestUpdateParams, ShipLatestLocalCollection
from .user_recent import UserRecentUpdateParams
from .user_summary import UserSummaryUpdateParams, UserSummaryLocalEntry


@dataclass(slots=True)
class LocalDataEntry:
    """保存某个模式的本地概览和船只缓存"""

    mode: ModeLatestLocalEntry
    ship: ShipLatestLocalCollection

    @property
    def battles(self) -> int:
        """返回本地数据库中的战斗场次"""
        return self.mode.battles

    @property
    def mode_index(self) -> int | None:
        """返回本地数据库中的数据索引"""
        return self.mode.mode_index

class UpdatePlan:
    """记录所有计划写入数据库的操作"""
    ship_map: ShipMapUpdateParams
    ship_data: ShipDataUpdateParams
    mode_latest: ModeLatestUpdateParams
    ship_latest: ShipLatestUpdateParams
    user_recent: UserRecentUpdateParams
    user_summary: UserSummaryUpdateParams

    def __init__(self) -> None:
        self.ship_map = ShipMapUpdateParams()
        self.ship_data = ShipDataUpdateParams()
        self.mode_latest = ModeLatestUpdateParams()
        self.ship_latest = ShipLatestUpdateParams()
        self.user_recent = UserRecentUpdateParams()
        self.user_summary = UserSummaryUpdateParams()

    @property
    def planned_count(self) -> int:
        """返回本次计划涉及的记录数"""
        return sum((
            self.user_summary.count,
            self.mode_latest.count,
            self.ship_latest.count,
            self.ship_map.count,
            self.ship_data.count,
            self.user_recent.count
        ))


__all__ = [
    'UpdatePlan',
    'ShipMapUpdateParams',
    'ShipDataUpdateParams',
    'ModeLatestUpdateParams',
    'LocalDataEntry',
    'ModeLatestLocalEntry',
    'ShipLatestUpdateParams',
    'ShipLatestLocalCollection',
    'UserRecentUpdateParams',
    'UserSummaryUpdateParams',
    'UserSummaryLocalEntry'
]
