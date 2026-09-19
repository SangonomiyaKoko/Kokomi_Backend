from dataclasses import dataclass
from typing import Optional

from shard import TimeUtils

from ..models import (
    TeamStats,
    ClanSeasonStats,
    STAR_FILLED,
    STAR_EMPTY
)


@dataclass(frozen=True, slots=True)
class StageInfo:
    """晋级赛阶段的解析结果"""
    stage_type: Optional[int] = None
    battles: int = 0
    victories: int = 0
    progress: Optional[str] = None


class ClanStatsParser:
    """公会详情响应的解析器"""

    @classmethod
    def main(
        cls, 
        season_id: int, 
        clan_id: int, 
        raw_data: dict
    ) -> ClanSeasonStats:
        """从 API 响应构建公会的赛季统计"""
        # 理论上 ru 不再参与本服务的统计
        # ladder_name = 'mk_ladder' if REGION == 'ru' else 'wows_ladder'
        # ladder = raw_data['clanview'][ladder_name]
        ladder = raw_data['clanview']['wows_ladder']

        team_data: dict[int, TeamStats] = {}
        stage_map: dict[int, StageInfo] = {}

        for team in ladder['ratings']:
            if team['season_number'] != season_id:
                continue

            team_number = team['team_number']
            stage = cls._parse_stage(team.get('stage'))
            stage_map[team_number] = stage
            team_data[team_number] = cls._parse_team(team, stage)

        # 确保每个 team_number 都存在
        # 理论上仅有 alpha 和 bravo 两个队伍
        for number in (1, 2):
            if not team_data.get(number):
                team_data[number] = TeamStats.from_list([])
            if not stage_map.get(number):
                stage_map[number] = StageInfo()

        # 分数领先队伍的 Index
        leading = ladder['leading_team_number']
        # 只有领先队伍的晋级赛数据计入公会整体统计

        lbt = TimeUtils.formtime_to_timestamp(
            formtime=ladder['last_battle_at']
        )

        return ClanSeasonStats(
            clan_id=clan_id,
            season_id=season_id,
            leading_team_number=leading,
            battles_count=ladder['battles_count'],
            wins_count=ladder['wins_count'],
            public_rating=ladder['public_rating'],
            league=ladder['league'],
            division=ladder['division'],
            division_rating=ladder['division_rating'],
            longest_winning_streak=ladder['longest_winning_streak'],
            stage_type=stage_map[leading].stage_type,
            stage_battles=stage_map[leading].battles,
            stage_victories=stage_map[leading].victories,
            stage_progress=stage_map[leading].progress,
            last_battle_time=lbt,
            team_alpha=team_data.get(1),
            team_bravo=team_data.get(2)
        )

    @staticmethod
    def _parse_team(team: dict, stage: StageInfo) -> TeamStats:
        """解析单个队伍的统计快照"""
        return TeamStats(
            battles_count=team['battles_count'],
            wins_count=team['wins_count'],
            public_rating=team['public_rating'],
            league=team['league'],
            division=team['division'],
            division_rating=team['division_rating'],
            stage_type=stage.stage_type,
            stage_progress=stage.progress
        )

    @staticmethod
    def _parse_stage(stage: Optional[dict]) -> StageInfo:
        """解析晋级赛阶段数据，非晋级赛返回空结果"""
        if not stage:
            return StageInfo()

        stage_type = stage.get('type')
        if not stage_type:
            return StageInfo()

        # 定义晋级赛/保级赛字段的index
        # 晋级赛 promotion -> 1
        # 保级赛 demotion  -> 2
        stage_index = 1 if stage_type == 'promotion' else 2
        progress_parts = []
        victories = 0
        for progress in stage.get('progress', []):
            if progress == 'victory':
                victories += 1
                progress_parts.append(STAR_FILLED)
            else:
                progress_parts.append(STAR_EMPTY)

        return StageInfo(
            stage_type=stage_index,
            battles=len(progress_parts),
            victories=victories,
            progress=''.join(progress_parts)
        )
