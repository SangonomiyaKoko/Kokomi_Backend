from app.database import MySQLManager
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.utils import RatingUtils, GameUtils, StringUtils

class RankingModel:
    @ExceptionLogger.handle_database_exception_async
    async def get_ship_leaderboard(ship_id: int, account_ids: list[str], dogtag: bool = False):
        """根据用户ID列表，从数据库中批量读取排行榜数据"""
        async with MySQLManager.read_only_cursor() as cur:
            placeholders = ','.join(['%s'] * len(account_ids))
            sql = f"""
                SELECT 
                    s.account_id,
                    u.clan_id,
                    u.clan_tag,
                    u.league,
                    u.username,
                    u.insignias,
                    s.battles,
                    s.rating,
                    ROUND(s.win_rate, 2) AS win_rate,
                    s.avg_damage,
                    s.avg_damage_level AS avg_damage_level,
                    s.avg_frags,
                    s.avg_frags_level AS avg_frags_level,
                    s.avg_exp,
                    ROUND(s.hit_ratio, 2) AS hit_ratio,
                    s.max_exp,
                    s.max_damage
                FROM T_ship_pvp_leaderboard s
                LEFT JOIN V_user_basic_with_clan u
                    ON s.account_id = u.account_id
                WHERE s.account_id IN ({placeholders})
                  AND s.ship_id = %s;
            """
            await cur.execute(sql, account_ids + [ship_id])
            rows = await cur.fetchall()
            result = {}
            for row in rows:
                account_id = str(row[0])
                result[account_id] = {
                    'clan_id': row[1],
                    'clan_tag': row[2],
                    'league': row[3],
                    'username': row[4],
                    'dogtag': None,
                    'battles': row[6],
                    'rating': row[7],
                    'win_rate': row[8],
                    'win_rate_level': RatingUtils.get_metric_level(0, row[8]),
                    'avg_damage': row[9],
                    'avg_damage_level': row[10],
                    'avg_frags': row[11],
                    'avg_frags_level': row[12],
                    'avg_exp': row[13],
                    'hit_ratio': row[14],
                    'max_exp': row[15],
                    'max_damage': row[16]
                }
                if dogtag:
                    result[account_id]['dogtag'] = StringUtils.parse_insignias(row[5])
            
            return JSONResponse.success(result)

    @ExceptionLogger.handle_database_exception_async
    async def get_clan_leaderboard(clan_ids: list[str]):
        """根据用户ID列表，从数据库中批量读取排行榜数据"""
        async with MySQLManager.read_only_cursor() as cur:
            placeholders = ','.join(['%s'] * len(clan_ids))
            sql = f"""
                SELECT 
                    s.clan_id,
                    b.tag,
                    s.leading_team,
                    s.battles,
                    s.win_rate,
                    CASE
                        WHEN s.battles = 0 THEN 0
                        WHEN s.win_rate < 40 THEN 1
                        WHEN s.win_rate < 45 THEN 2
                        WHEN s.win_rate < 50 THEN 3
                        WHEN s.win_rate < 52.5 THEN 4
                        WHEN s.win_rate < 55 THEN 5
                        WHEN s.win_rate < 60 THEN 6
                        WHEN s.win_rate < 67 THEN 7
                        ELSE 8
                    END,
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
            await cur.execute(sql, clan_ids)
            rows = await cur.fetchall()
            result = {}
            for row in rows:
                clan_id = str(row[0])
                result[clan_id] = {
                    'tag': row[1],
                    'leading_team': row[2],
                    'battles': row[3],
                    'win_rate': row[4],
                    'win_rate_level': row[5],
                    'league': row[6],
                    'division': row[7],
                    'rating': row[8],
                    'max_streak': row[9],
                    'stage_type': row[10],
                    'stage_progress': row[11],
                    'last_battle_at': row[12]
                }
            
            return JSONResponse.success(result)