import json
from pymysql.cursors import Cursor

from utils import get_rating_level
from settings import (
    MAX_REFRESH_BATCH,
    METRIC_ID_TO_INDEX, 
    INDEX_TO_METRIC_ID
)


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
          AND is_old = 1;
    """
    cursor.execute(sql)
    return [str(row[0]) for row in cursor.fetchall()]

def read_disabled_ship_ids(cursor: Cursor) -> list:
    sql = f"""
        SELECT 
            ship_id 
        FROM T_ship_base
        WHERE is_enabled = 0 OR is_old = 1;
    """
    cursor.execute(sql)
    return [str(row[0]) for row in cursor.fetchall()]

def read_ship_record(cursor: Cursor) -> dict:
    """读取船只 PvP 极值记录数据（返回用户ID集合）

    按 ship_id 和 metric_id 分组，将各指标的最高值、达成人数和达成用户集合
    组织为嵌套字典结构。

    Args:
        cursor: 数据库游标

    Returns:
        字典，键为 ship_id (str)，值为按 METRIC_ID_TO_INDEX 顺序排列的
        [[metric_value, users_count, top_user_ids], ...] 列表，
        其中 top_user_ids 始终为 set 类型（可能为空 set）。
    """
    result = {}
    
    metric_ids = list(METRIC_ID_TO_INDEX.keys())
    placeholders = ','.join(['%s'] * len(metric_ids))
    sql = f"""
        SELECT 
            ship_id,
            metric_id,
            metric_value,
            users_count,
            top_user_ids
        FROM T_ship_pvp_record
        WHERE metric_id IN ({placeholders});
    """
    cursor.execute(sql, metric_ids)
    
    for row in cursor.fetchall():
        ship_id = str(row[0])
        metric_id = row[1]
        metric_value = row[2]
        users_count = row[3]
        top_user_ids_raw = row[4]  # JSON 字符串或 None
        
        # 转换为 set，NULL 或空数组均得到空集合
        if top_user_ids_raw is not None:
            top_user_ids = set(json.loads(top_user_ids_raw))
        else:
            top_user_ids = set()
        
        if ship_id not in result:
            # 初始化：每个指标默认 [0, 0, set()]
            result[ship_id] = [[0, 0, set()] for _ in range(len(METRIC_ID_TO_INDEX))]
        
        idx = METRIC_ID_TO_INDEX[metric_id]
        result[ship_id][idx] = [metric_value, users_count, top_user_ids]
    
    return result

def update_ship_record(cursor: Cursor, data: dict) -> None:
    """将船只 PvP 极值记录字典写回数据库

    根据传入的嵌套字典结构，更新 T_ship_pvp_record 表中的记录

    Args:
        cursor: 数据库游标
        data: 与 read_ship_record 返回值结构相同的字典
    """
    sql = """
        UPDATE T_ship_pvp_record 
        SET 
            metric_value = %s,
            users_count = %s,
            top_user_ids = %s
        WHERE 
            ship_id = %s AND metric_id = %s
    """
    
    params_list = []
    for ship_id, metrics in data.items():
        for idx, record in enumerate(metrics):
            # record 结构: [metric_value, users_count, top_user_ids_set]
            if not record:
                continue
            metric_value, users_count, top_user_ids_set = record
            metric_id = INDEX_TO_METRIC_ID[idx]
            # 将 set 转换为 JSON 数组字符串
            top_user_ids_json = json.dumps(list(top_user_ids_set)) if top_user_ids_set is not None else None
            params_list.append((metric_value, users_count, top_user_ids_json, ship_id, metric_id))
    
    if len(params_list) == 0:
        return 0
    
    cursor.executemany(sql, params_list)
    return cursor.rowcount

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
            s.max_damage
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
            round(row[6], 2), get_rating_level(row[6], 'win_rate'),
            row[7], row[8], row[9], row[10],
            row[11], row[12], row[13], row[14]
        ]
    
    payload = []
    for i, user_id in enumerate(account_ids):
        payload.append([i+1, int(user_id)] + result.get(user_id))

    return payload