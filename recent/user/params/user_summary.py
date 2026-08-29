from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, List, Tuple, Any

from models import BattleMode, UserStats


@dataclass(frozen=True, slots=True)
class UserSummaryLocalEntry:
    """user_daily_summary 表的一行数据"""
    is_public: bool
    total_battles: int
    pve_battles: int
    pvp_battles: int
    rank_battles: int
    clan_battles: int
    karma: int
    pvp_index: Optional[int]
    rank_index: Optional[int]
    clan_index: Optional[int]
    updated_at: int

    def map_index(self, mode: BattleMode) -> Optional[int]:
        """获取指定模式的统计索引"""
        if mode == BattleMode.PVP:
            return self.pvp_index
        if mode == BattleMode.RANK:
            return self.rank_index
        if mode == BattleMode.CLAN:
            return self.clan_index
        raise ValueError('Invalid mode')

    def to_list(self) -> list:
        """转换为数据库字段列表"""
        return [
            self.is_public, self.total_battles, self.pve_battles, self.pvp_battles,
            self.rank_battles, self.clan_battles, self.karma, self.pvp_index,
            self.rank_index, self.clan_index, self.updated_at
        ]

    @classmethod
    def from_row(cls, row: tuple) -> UserSummaryLocalEntry:
        """从数据库查询结果 tuple 构造实例"""
        return cls(
            is_public=bool(row[0]),
            total_battles=row[1],
            pve_battles=row[2],
            pvp_battles=row[3],
            rank_battles=row[4],
            clan_battles=row[5],
            karma=row[6],
            pvp_index=row[7],
            rank_index=row[8],
            clan_index=row[9],
            updated_at=row[10]
        )


@dataclass(frozen=True, slots=True)
class UserSummaryUpdateEntry:
    snapshot_date: int
    is_public: bool
    total_battles: int
    pve_battles: int
    pvp_battles: int
    rank_battles: int
    clan_battles: int
    karma: int
    pvp_index: Optional[int]
    rank_index: Optional[int]
    clan_index: Optional[int]
    update_time: int

    def as_insert_params(self) -> tuple:
        """转换为数据库插入参数"""
        return (
            self.snapshot_date, self.is_public, self.total_battles,
            self.pve_battles, self.pvp_battles, self.rank_battles,
            self.clan_battles, self.karma, self.pvp_index, self.rank_index,
            self.clan_index, self.update_time
        )

    def as_update_params(self) -> tuple:
        """转换为数据库更新参数"""
        return (
            self.is_public, self.total_battles, self.pve_battles,
            self.pvp_battles, self.rank_battles, self.clan_battles,
            self.karma, self.pvp_index, self.rank_index, self.clan_index,
            self.update_time, self.snapshot_date
        )

    @classmethod
    def from_hidden(
        cls, snapshot_date: int, updated_at: int
    ) -> UserSummaryUpdateEntry:
        """创建隐藏状态的摘要更新记录"""
        return cls(
            snapshot_date=snapshot_date,
            is_public=False,
            total_battles=0,
            pve_battles=0,
            pvp_battles=0,
            rank_battles=0,
            clan_battles=0,
            karma=0,
            pvp_index=None,
            rank_index=None,
            clan_index=None,
            update_time=updated_at
        )

    @classmethod
    def from_stats(
        cls, snapshot_date: int, stats: UserStats, indices: Dict[BattleMode, Optional[int]]
    ) -> UserSummaryUpdateEntry:
        """根据最新统计创建摘要记录"""
        return cls(
            snapshot_date=snapshot_date,
            is_public=stats.is_public,
            total_battles=stats.total_battles,
            pve_battles=stats.pve_battles,
            pvp_battles=stats.pvp_battles,
            rank_battles=stats.ranked_battles,
            clan_battles=stats.rating_battles,
            karma=stats.karma,
            pvp_index=indices.get(BattleMode.PVP),
            rank_index=indices.get(BattleMode.RANK),
            clan_index=indices.get(BattleMode.CLAN),
            update_time=stats.updated_at
        )

    @classmethod
    def from_local(
        cls, snapshot_date: int, summary: UserSummaryLocalEntry
    ) -> UserSummaryUpdateEntry:
        """根据本地摘要创建更新记录"""
        return cls(
            snapshot_date=snapshot_date,
            is_public=summary.is_public,
            total_battles=summary.total_battles,
            pve_battles=summary.pve_battles,
            pvp_battles=summary.pvp_battles,
            rank_battles=summary.rank_battles,
            clan_battles=summary.clan_battles,
            karma=summary.karma,
            pvp_index=summary.pvp_index,
            rank_index=summary.rank_index,
            clan_index=summary.clan_index,
            update_time=summary.updated_at
        )

@dataclass
class UserSummaryUpdateParams:
    insert: list[UserSummaryUpdateEntry] = field(default_factory=list)
    update: list[UserSummaryUpdateEntry] = field(default_factory=list)

    @property
    def count(self) -> int:
        """返回待处理记录数"""
        return len(self.insert) + len(self.update)

    @property
    def has_update_params(self) -> bool:
        """判断是否存在更新参数"""
        return len(self.update) > 0

    @property
    def get_update_params(self) -> List[Tuple[Any]]:
        """返回数据库更新参数列表"""
        return [p.as_update_params() for p in self.update]

    def set_update_params_from_hidden(
        self, snapshot_date: int, updated_at: int
    ) -> None:
        """添加隐藏状态更新参数"""
        self.update.append(
            UserSummaryUpdateEntry.from_hidden(snapshot_date, updated_at)
        )

    def set_update_params_from_stats(
        self, snapshot_date: int, stats: UserStats, indices: Dict[BattleMode, Optional[int]]
    ) -> None:
        """添加最新统计更新参数"""
        self.update.append(
            UserSummaryUpdateEntry.from_stats(snapshot_date, stats, indices)
        )

    def set_update_params_from_local(
        self, snapshot_date: int, summary: UserSummaryLocalEntry
    ) -> None:
        """添加本地摘要更新参数"""
        self.update.append(
            UserSummaryUpdateEntry.from_local(snapshot_date, summary)
        )

    @property
    def has_insert_params(self) -> bool:
        """判断是否存在插入参数"""
        return len(self.insert) > 0

    @property
    def get_insert_params(self) -> List[Tuple[Any]]:
        """返回数据库插入参数列表"""
        return [p.as_insert_params() for p in self.insert]

    def set_insert_params_from_stats(
        self, snapshot_date: int, stats: UserStats, indices: Dict[BattleMode, Optional[int]]
    ) -> None:
        """添加最新统计插入参数"""
        self.insert.append(
            UserSummaryUpdateEntry.from_stats(snapshot_date, stats, indices)
        )
