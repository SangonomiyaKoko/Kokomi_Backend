from dataclasses import dataclass

from .user import UserStats, UserRecord
from .mode import BattleMode, DataType, UpdateStrategy
from .reason import (
    SkipReason,
    UpdateReason,
    DisableReason,
    UpdateResult,
    ValidationResult
)
from .stats import (
    ShipBattleStats,
    ModeBattleStats,
    ShipDataEntry,
    ShipDataCollection
)


@dataclass(slots=True)
class LatestDataEntry:
    """保存某个模式的概览数据和船只数据"""

    mode: ModeBattleStats
    ship: ShipDataCollection

    @property
    def battles(self) -> int:
        """返回该模式的总战斗场次"""
        return self.mode.battles

BASE_UPDATE_MODES = {BattleMode.PVP, BattleMode.RANK}
FULL_UPDATE_MODES = {BattleMode.PVP, BattleMode.RANK, BattleMode.CLAN}


__all__ = [
    'UserStats',
    'UserRecord',
    'DataType',
    'BattleMode',
    'UpdateStrategy',
    'SkipReason',
    'UpdateReason',
    'DisableReason',
    'UpdateResult',
    'ValidationResult',
    'LatestDataEntry',
    'ShipBattleStats',
    'ModeBattleStats',
    'ShipDataEntry',
    'ShipDataCollection',
    'BASE_UPDATE_MODES',
    'FULL_UPDATE_MODES'
]
