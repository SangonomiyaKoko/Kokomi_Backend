from typing import Optional

from pymysql.cursors import Cursor
from shard import RatingAlgo

from ..models import ClanTeamCache, ClanSeasonStats


class ClanStatsRepository:

    @staticmethod
    def load_team_cache(
        cursor: Cursor, clan_id: int
    ) -> Optional[ClanTeamCache]:
        """读取单个公会缓存的赛季与队伍数据"""
        sql = """
            SELECT
                season,
                team_alpha,
                team_bravo
            FROM T_clan_team
            WHERE clan_id = %s;
        """
        cursor.execute(sql, [clan_id])
        row = cursor.fetchone()
        if not row:
            return None

        return ClanTeamCache.from_row(row)


    @staticmethod
    def load_leaderboard(
        cursor: Cursor, clan_ids: list
    ) -> dict[str, list]:
        """根据公会 ID 列表批量读取排行榜数据"""
        if not clan_ids:
            return {}

        placeholders = ','.join(['%s'] * len(clan_ids))
        sql = f"""
            SELECT
                s.clan_id,
                b.tag,
                s.leading_team,
                s.battles,
                s.win_rate,
                s.league,
                s.division,
                s.public_rating,
                s.max_streak,
                s.stage_type,
                s.stage_progress,
                UNIX_TIMESTAMP(s.last_battle_at)
            FROM T_clan_stats s
            LEFT JOIN T_clan_base b
                ON s.clan_id = b.clan_id
            WHERE s.clan_id IN ({placeholders});
        """
        cursor.execute(sql, clan_ids)

        result = {}
        for row in cursor.fetchall():
            (clan_id, tag, leading_team, battles, win_rate, league, division,
             public_rating, max_streak, stage_type, stage_progress,
             last_battle_at) = row

            result[str(clan_id)] = [
                tag,
                leading_team,
                battles,
                win_rate,
                RatingAlgo.get_metric_level(
                    value=win_rate,
                    metric_name='win_rate'
                ),
                league,
                division,
                public_rating,
                max_streak,
                stage_type,
                stage_progress,
                last_battle_at
            ]

        return result
    
    @staticmethod
    def update_teams(
        cursor: Cursor, stats: ClanSeasonStats
    ) -> None:
        """更新 T_clan_team 中的赛季与队伍数据

        基线队伍以 NULL 写入，读取时由 TeamStats 还原为 SEASON_BASELINE；
        参数顺序需与下列 SET 子句保持一致
        """
        sql = """
            UPDATE T_clan_team
            SET
                season = %s,
                team_alpha = %s,
                team_bravo = %s,
                updated_at = NOW()
            WHERE clan_id = %s
        """
        cursor.execute(sql, [
            stats.season_id,
            stats.team_json(1),
            stats.team_json(2),
            stats.clan_id
        ])

    @staticmethod
    def update_stats(
        cursor: Cursor, stats: ClanSeasonStats
    ) -> None:
        """更新 T_clan_stats 中的公会赛季统计

        public_rating 写入的是由公开评分与晋级赛战绩合成的综合评分，
        参数顺序需与下列 SET 子句保持一致
        """
        sql = """
            UPDATE T_clan_stats
            SET
                season = %s,
                leading_team = %s,
                battles = %s,
                win_rate = %s,
                public_rating = %s,
                league = %s,
                division = %s,
                division_rating = %s,
                max_streak = %s,
                stage_type = %s,
                stage_progress = %s,
                last_battle_at = FROM_UNIXTIME(%s),
                updated_at = NOW()
            WHERE clan_id = %s
        """
        cursor.execute(sql, [
            stats.season_id,
            stats.leading_team_number,
            stats.battles_count,
            stats.win_rate,
            stats.clan_rating,
            stats.league,
            stats.division,
            stats.division_rating,
            stats.longest_winning_streak,
            stats.stage_type,
            stats.stage_progress,
            stats.last_battle_time,
            stats.clan_id
        ])
