from pymysql.cursors import Cursor

from shard import RatingUtils

from .settings import MAX_REFRESH_BATCH


def read_game_version(cursor: Cursor) -> tuple:
    sql = """
        SELECT 
            short_name,
            UNIX_TIMESTAMP(created_at) 
        FROM T_game_version 
        WHERE is_latest = TRUE 
        LIMIT 1;
    """
    cursor.execute(sql)
    version = cursor.fetchone()
    if not version:
        return None, None
    else:
        return version[0], version[1]

def read_enabled_ship_ids(cursor: Cursor) -> list:
    sql = f"""
        SELECT 
            ship_id 
        FROM T_ship_base
        WHERE is_enabled = 1 
          AND is_old = 0;
    """
    cursor.execute(sql)
    return [str(row[0]) for row in cursor.fetchall()]

def read_ship_data(cursor: Cursor) -> dict:
    """加载船只排行榜基准数据

    从视图读取每艘船的最低场次要求和服务器场均指标，
    用于计算玩家 Rating 的基准值

    Args:
        cursor: 数据库游标

    Returns:
        字典，键为 ship_id，值为 [min_battles, [win_rate, avg_damage, avg_frags]]
    """
    ship_info = {}
    sql = """
        SELECT 
            ship_id, 
            min_battles, 
            stats_battles, 
            win_rate, 
            avg_damage, 
            avg_frags
        FROM V_ship_ranking_stats;
    """
    cursor.execute(sql)
    rows = cursor.fetchall()
    for row in rows:
        if row[2] < 1000:
            ship_info[str(row[0])] = [
                row[1],
                None
            ]
        else:
            ship_info[str(row[0])] = [
                row[1],
                [row[3], row[4], row[5]]
            ]
    return ship_info

def get_update_ids(cursor: Cursor) -> list:
    """获取需要更新 PvP 缓存的用户 ID 列表

    Args:
        cursor: 数据库游标

    Returns:
        account_id 列表
    """
    sql = """
        SELECT 
            account_id
        FROM T_user_cache 
        WHERE is_due = 1
        LIMIT %s;
    """
    cursor.execute(sql, [MAX_REFRESH_BATCH])
    return [row[0] for row in cursor.fetchall()]

def get_ship_leaderboard(cursor: Cursor, ship_id: int, account_ids: list[str]):
    """根据用户ID列表，从数据库中批量读取排行榜数据"""
    placeholders = ','.join(['%s'] * len(account_ids))
    sql = f"""
        SELECT 
            s.account_id,
            u.clan_tag,
            u.league,
            u.username,
            s.battles,
            s.rating,
            s.win_rate,
            s.avg_damage,
            s.avg_damage_level,
            s.avg_frags,
            s.avg_frags_level,
            s.avg_exp,
            s.hit_ratio,
            s.max_exp,
            s.max_damage,
            u.insignias
        FROM T_ship_pvp_leaderboard s
        LEFT JOIN V_user_basic_with_clan u
            ON s.account_id = u.account_id
        WHERE s.account_id IN ({placeholders})
            AND s.ship_id = %s;
    """
    cursor.execute(sql, account_ids + [ship_id])
    rows = cursor.fetchall()

    result = {}
    for row in rows:
        account_id = str(row[0])
        result[account_id] = [
            row[1], row[2], row[3], row[4], row[5], 
            round(row[6], 2), RatingUtils.get_metric_level(row[6], 'win_rate'),
            row[7], row[8], row[9], row[10],
            row[11], row[12], row[13], row[14], row[15]
        ]
    
    payload = []
    for i, user_id in enumerate(account_ids):
        payload.append([i+1, int(user_id)] + result.get(user_id))

    return payload