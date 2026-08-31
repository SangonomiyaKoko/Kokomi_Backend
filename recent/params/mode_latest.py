from dataclasses import dataclass, field
from typing import List, Tuple, Any, Optional

from models import BattleMode, ModeBattleStats


@dataclass(frozen=True, slots=True)
class ModeLatestLocalEntry:
    """本地数据库中记录的一个模式的统计数据"""
    battles: int
    mode_index: Optional[int]
    update_time: Optional[int]


@dataclass(frozen=True, slots=True)
class ModeLatestUpdateEntry:
    ship_mode: int
    battles: int = 0
    win_rate: float = 0.0
    avg_damage: int = 0
    avg_frags: float = 0.0
    avg_exp: int = 0
    mode_index: Optional[int] = None
    update_time: Optional[int] = None

    def as_update_params(self) -> tuple:
        """转换为数据库更新参数"""
        return (
            self.battles, self.win_rate, self.avg_damage, self.avg_frags,
            self.avg_exp, self.mode_index, self.update_time, self.ship_mode
        )


@dataclass
class ModeLatestUpdateParams:
    update: list[ModeLatestUpdateEntry] = field(default_factory=list)
    clan_special_update_params: int | None = None

    @property
    def count(self) -> int:
        """返回待更新记录数"""
        return len(self.update) + (1 if self.clan_special_update_params else 0)

    @property
    def has_params(self) -> bool:
        """判断是否没有更新参数"""
        return len(self.update) == 0

    @property
    def has_update_params(self) -> bool:
        """判断是否存在更新参数"""
        return len(self.update) > 0

    @property
    def get_update_params(self) -> List[Tuple[Any]]:
        """返回数据库更新参数列表"""
        return [p.as_update_params() for p in self.update]

    def set_update_params(
        self, ship_mode: BattleMode, mode_data: ModeBattleStats, mode_index: int, updated_at: int
    ) -> None:
        """添加一条模式概览更新参数"""
        mode_rates_data = mode_data.rates()
        self.update.append(
            ModeLatestUpdateEntry(
                ship_mode=ship_mode.value,
                battles=mode_data.battles,
                win_rate=mode_rates_data[0],
                avg_damage=mode_rates_data[1],
                avg_frags=mode_rates_data[2],
                avg_exp=mode_rates_data[3],
                mode_index=mode_index,
                update_time=updated_at
            )
        )

    @property
    def has_special_params(self) -> bool:
        """判断是否存在更新参数"""
        return self.clan_special_update_params is not None

    def set_special_params(self, updated_at: int):
        self.clan_special_update_params = updated_at
