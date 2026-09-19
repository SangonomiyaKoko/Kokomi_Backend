from __future__ import annotations

import json
from dataclasses import dataclass, astuple
from typing import List, Optional

from shard import TimeUtils


PROMOTION = '▲'     # 晋级 ▲
DEMOTION = '▼'      # 降级 ▼
STAR_FILLED = '★'  # ★
STAR_EMPTY = '☆'   # ☆

# 新赛季基线数据
# 公会尚未参加本赛季时 API 不返回队伍数据，以该基线作为新旧对比的起点
BASELINE_RATING = 1100
SEASON_BASELINE = (0, 0, BASELINE_RATING, 4, 2, 50, None, None)


@dataclass(frozen=True, slots=True)
class TeamStats:
    """单个队伍在赛季中的统计快照"""
    battles_count: int
    wins_count: int
    public_rating: int
    league: int
    division: int
    division_rating: int
    stage_type: Optional[int]
    stage_progress: Optional[str]

    @classmethod
    def from_list(cls, data: list) -> TeamStats:
        """由 8 元素数组创建，数组为空时返回赛季基线

        API 返回的队伍数组与 T_clan_team 中缓存的数组结构一致，
        因此两条读取路径共用本方法，下标映射只在此处定义一次
        """
        return cls(*(data if data else SEASON_BASELINE))

    @property
    def is_baseline(self) -> bool:
        """是否处于未参战的基线状态

        T_clan_team 中以 NULL 表示该状态，避免为绝大多数未参战公会
        存储冗余数据；但初始分不为基线的公会即便尚未开战也必须落库，
        否则首场战斗统计不出正确的分差
        """
        return (
            self.battles_count == 0
            and self.public_rating == BASELINE_RATING
        )

    def to_list(self) -> List:
        """转换为列表格式，用于序列化"""
        return list(astuple(self))


@dataclass(frozen=True, slots=True)
class LeagueClanEntry:
    """排行榜接口返回的单个公会条目"""
    clan_id: int
    tag: str
    league: str
    last_battle_time: Optional[int]
    season_id: int

    @classmethod
    def from_api(cls, data: dict, league: str) -> LeagueClanEntry:
        """从 API 响应条目创建 LeagueClanEntry 对象"""
        return cls(
            clan_id=data['id'],
            tag=data['tag'],
            league=league,
            last_battle_time=TimeUtils.formtime_to_timestamp(
                data['last_battle_at']
            ),
            season_id=data['season_number']
        )


@dataclass(frozen=True, slots=True)
class ClanRecord:
    """T_clan_stats 中记录的公会赛季状态"""
    clan_id: int
    season: Optional[int]
    last_battle_time: Optional[int]

    @classmethod
    def from_row(cls, row: tuple) -> ClanRecord:
        """从数据库行创建 ClanRecord 对象"""
        return cls(
            clan_id=row[0],
            season=row[1],
            last_battle_time=row[2]
        )


@dataclass(frozen=True, slots=True)
class ClanTeamCache:
    """T_clan_team 中缓存的赛季与队伍数据"""
    season: Optional[int]
    team_alpha: TeamStats
    team_bravo: TeamStats

    @classmethod
    def from_row(cls, row: tuple) -> ClanTeamCache:
        """从数据库行创建 ClanTeamCache 对象，队伍数据已解码

        NULL 表示该队伍仍处于赛季基线状态，交由 TeamStats 还原
        """
        team_alpha = TeamStats.from_list(
            data=json.loads(row[1]) if row[1] else []
        )
        team_bravo = TeamStats.from_list(
            data=json.loads(row[2]) if row[2] else []
        )
        return cls(
            season=row[0],
            team_alpha=team_alpha,
            team_bravo=team_bravo
        )


@dataclass(frozen=True, slots=True)
class BattleRecord:
    """一条对战明细，字段顺序与 clan_battle 表一致"""
    battle_time: int
    clan_id: int
    team_number: int
    victory: int
    result: str
    rating: int
    league: int
    division: int
    division_rating: int
    stage_type: Optional[int]
    stage_progress: Optional[str]

    def to_list(self) -> List:
        """转换为插入 clan_battle 所需的参数列表"""
        return list(astuple(self))


@dataclass(frozen=True, slots=True)
class ClanSeasonStats:
    """单个公会的最新赛季统计，由 API 响应解析而来"""
    clan_id: int
    season_id: int
    leading_team_number: int
    battles_count: int
    wins_count: int
    public_rating: int
    league: int
    division: int
    division_rating: int
    longest_winning_streak: int
    stage_type: Optional[int]
    stage_battles: int
    stage_victories: int
    stage_progress: Optional[str]
    last_battle_time: int
    team_alpha: TeamStats
    team_bravo: TeamStats

    @property
    def win_rate(self) -> float:
        """胜率（百分比，保留两位小数）"""
        if self.battles_count <= 0:
            return 0.0

        return round((self.wins_count / self.battles_count) * 100, 2)

    @property
    def clan_rating(self) -> float:
        """公会综合评分，由公开评分与晋级赛战绩计算而来

        写入 T_clan_stats.public_rating，并用于 Redis 排行榜排序
        """
        return round(
            self.public_rating
            + self.stage_battles * 0.1
            + self.stage_victories * 0.01,
            2
        )

    def team_json(self, team_number: int) -> Optional[str]:
        """单支队伍的序列化结果，用于写入 T_clan_team

        基线状态写入 None，与 SEASON_BASELINE 等价
        """
        team = self.team_alpha if team_number == 1 else self.team_bravo
        if team.is_baseline:
            return None

        return json.dumps(team.to_list())
