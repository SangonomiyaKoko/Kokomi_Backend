from dataclasses import dataclass, field
from typing import List, Tuple, Any

from models import BattleMode, DataType


@dataclass(frozen=True, slots=True)
class UserRecentUpdateEntry:
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
        """转换为数据库插入参数"""
        return (
            self.ship_id, self.data_mode, self.data_type, self.battles,
            self.wins, self.losses, self.exp, self.damage, self.planes,
            self.frags, self.survived, self.scout_damage, self.art_agro,
            self.hit_rate, self.battle_time
        )


@dataclass
class UserRecentUpdateParams:
    insert: list[UserRecentUpdateEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        """返回待插入记录数"""
        return len(self.insert)

    @property
    def has_params(self) -> bool:
        """判断是否没有待插入参数"""
        return len(self.insert) == 0

    @property
    def has_insert_params(self) -> bool:
        """判断是否存在插入参数"""
        return len(self.insert) > 0

    @property
    def get_insert_params(self) -> List[Tuple[Any]]:
        """返回数据库插入参数列表"""
        return [p.as_insert_params() for p in self.insert]

    def set_insert_params(
        self,
        ship_id: int,
        ship_mode: BattleMode,
        data_type: DataType,
        battles: int,
        deltas: List[int],
        battle_time: int,
    ) -> None:
        """写入一条近期数据行

        deltas 为新旧快照各字段差值列表，顺序为
        (wins, losses, damage, frags, survived, scout_damage, art_agro, exp, planes, hits, shots)
        """
        hits, shots = deltas[9], deltas[10]
        self.insert.append(
            UserRecentUpdateEntry(
                ship_id=ship_id,
                data_mode=ship_mode.value,
                data_type=data_type.value,
                battles=battles,
                wins=deltas[0],
                losses=deltas[1],
                exp=deltas[7],
                damage=deltas[2],
                planes=deltas[8],
                frags=deltas[3],
                survived=deltas[4],
                scout_damage=deltas[5],
                art_agro=deltas[6],
                hit_rate=round(hits / shots * 100, 2) if shots != 0 else 0.0,
                battle_time=battle_time,
            )
        )
