import os
import time
import json
import traceback
import httpx
import sqlite3
import asyncio
from datetime import datetime, timezone
from logger import logger
from middlewares import redis_client
from utils import now_iso, del_recent, del_recents, update_base
from settings import DATA_DIR

VORTEX_API_URL_LIST = {
    1: 'https://vortex.worldofwarships.asia',
    2: 'https://vortex.worldofwarships.eu',
    3: 'https://vortex.worldofwarships.com',
    4: 'https://vortex.korabli.su',
    5: 'https://vortex.wowsgame.cn'
}

REGION_UTC_LIST = {
    1:8, 
    2:1, 
    3:-7, 
    4:3, 
    5:8
}

CreateSQL = """
CREATE TABLE user (
    date str PRIMARY KEY,
    is_public bool,
    leveling_points int,
    karma int,
    win_rate float,
    avg_damage float,
    avg_frags float,
    cache str
);
CREATE TABLE ships (
    ship_id str,
    date str,
    cache str
);
CREATE UNIQUE INDEX idx_ships ON ships(ship_id, date);
"""

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def varify_responses(responses: list | dict):
    error = 0
    error_return = None
    for response in responses:
        if type(response) == str:
            error += 1
            error_return = response
    if error == 0:
        return None, None
    else:
        return error, error_return

def formtimestamp(region_id: int, diff: int = 0):
    timestamp = time.time() + REGION_UTC_LIST[region_id]*3600 - 5*3600 - diff*24*60*60
    return datetime.fromtimestamp(timestamp, timezone.utc).strftime("%Y%m%d")

def diff_lists(new_data, old_data):
    battles = 0
    result = []
    for new_row, old_row in zip(new_data, old_data):
        if not new_row or not old_row:
            result.append([])
            continue
        row_diff = [n - o for n, o in zip(new_row, old_row)]
        if row_diff[0] == 0:
            result.append([])
            continue
        battles += row_diff[0]
        result.append(row_diff)
    if battles == 0:
        return None
    return result

async def fetch_data(url):
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(url, timeout=5)
            requset_code = res.status_code
            requset_result = res.json()
            if requset_code == 200:
                return requset_result['data']
            if requset_code == 404:
                return {}
            logger.warning(f'Code_{requset_code} {url}')
            return f'HTTP_STATUS_{requset_code}'
    except Exception as e:
        logger.warning(f"{type(e).__name__} {url}")
        return f'ERROR_{type(e).__name__}'

async def get_data(region_id: int, account_id: int, ac1: str = None):
    base_url = VORTEX_API_URL_LIST[region_id]
    if region_id == 4:
        urls = [
            f'{base_url}/api/accounts/{account_id}/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_solo/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div2/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div3/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/rank_solo/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/rating_solo/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/rating_div/' + (f'?ac={ac1}' if ac1 else '')
        ]
    else:
        urls = [
            f'{base_url}/api/accounts/{account_id}/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_solo/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div2/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div3/' + (f'?ac={ac1}' if ac1 else ''),
            f'{base_url}/api/accounts/{account_id}/ships/rank_solo/' + (f'?ac={ac1}' if ac1 else '')
        ]
    tasks = []
    responses = []
    async with asyncio.Semaphore(len(urls)):
        for url in urls:
            tasks.append(fetch_data(url))
        responses = await asyncio.gather(*tasks)
        return responses

def init_db_if_needed(
    db_path: str
) -> bool:
    """
    检查 sqlite3 数据库是否存在且包含用户表，
    若不存在或为空数据库，则创建表。
    """
    need_init = False
    # 文件是否存在
    if not os.path.exists(db_path):
        need_init = True
    try:
        # 连接数据库（不存在会自动创建）
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 检查是否存在用户表
        cursor.execute("""
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
              AND name NOT LIKE 'sqlite_%'
            LIMIT 1;
        """)
        has_table = cursor.fetchone() is not None
        if not has_table:
            need_init = True
        # 需要初始化 → 创建表
        if need_init:
            cursor.executescript(CreateSQL)
            conn.commit()
        return True
    except Exception:
        logger.error((f"{now_iso()} | {traceback.format_exc()}"))
        return False
    finally:
        if 'conn' in locals():
            conn.close()

def responeses_processing(responses: list):
    battles_dict = {}
    statis_dict = {}
    if len(responses) == 4:
        type_list = ['pvp_solo', 'pvp_div2', 'pvp_div3', 'rank_solo']
        i = 0
        for response in responses:
            for ship_id, ship_data in response.items():
                if ship_id not in battles_dict:
                    battles_dict[ship_id] = 0
                    statis_dict[ship_id] = [[],[],[],[]]
                battle_type = type_list[i]
                if ship_data[battle_type] != {}:
                    battles_dict[ship_id] += ship_data[battle_type]['battles_count']
                    statis_dict[ship_id][i] = [
                        ship_data[battle_type]['battles_count'],
                        ship_data[battle_type]['wins'],
                        ship_data[battle_type]['losses'],
                        ship_data[battle_type]['damage_dealt'],
                        ship_data[battle_type]['frags'],
                        ship_data[battle_type]['survived'],
                        ship_data[battle_type]['scouting_damage'],
                        ship_data[battle_type]['art_agro'],
                        ship_data[battle_type]['original_exp'],
                        ship_data[battle_type]['planes_killed'],
                        ship_data[battle_type]['hits_by_main'],
                        ship_data[battle_type]['shots_by_main']
                    ]
            i += 1
        return battles_dict, statis_dict
    else:
        type_list = ['pvp_solo', 'pvp_div2', 'pvp_div3', 'rank_solo', 'rating_solo', 'rating_div']
        i = 0
        for response in responses:
            for ship_id, ship_data in response.items():
                if ship_id not in battles_dict:
                    battles_dict[ship_id] = 0
                    statis_dict[ship_id] = [[],[],[],[],[],[]]
                battle_type = type_list[i]
                if ship_data[battle_type] != {}:
                    battles_dict[ship_id] += ship_data[battle_type]['battles_count']
                    statis_dict[ship_id][i] = [
                        ship_data[battle_type]['battles_count'],
                        ship_data[battle_type]['wins'],
                        ship_data[battle_type]['losses'],
                        ship_data[battle_type]['damage_dealt'],
                        ship_data[battle_type]['frags'],
                        ship_data[battle_type]['survived'],
                        ship_data[battle_type]['assist_damage'],
                        ship_data[battle_type]['art_agro'],
                        ship_data[battle_type]['original_exp'],
                        ship_data[battle_type]['planes_killed'],
                        ship_data[battle_type]['hits_by_main'],
                        ship_data[battle_type]['shots_by_main']
                    ]
            i += 1
        return battles_dict, statis_dict

async def update(
    region_id: int, 
    account_id: int, 
    enable_daily: bool, 
    total_battles: int,
    ac: str = None
):
    region_dict = {1: 'asia',2: 'eu',3: 'na',4: 'ru',5: 'cn'}
    region = region_dict[region_id]
    # 先检测db文件是否存在，不存在则创建
    db_path = os.path.join(DATA_DIR,'db',f'{region_id}',f'{account_id}.db')
    if init_db_if_needed(db_path) is False:
        return 'SQLite3InitializationError'
    # 获取当前和昨天的user表数据
    date_1 = formtimestamp(region_id, 0)
    date_2 = formtimestamp(region_id, 1)
    try:
        # 连接数据库（不存在会自动创建）
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 检查是否存在用户表
        cursor.execute("""
            SELECT 
                is_public, 
                leveling_points, 
                karma, 
                win_rate, 
                avg_damage, 
                avg_frags, 
                cache 
            FROM user 
            WHERE date = ?;
        """, [date_2])
        date2_data = cursor.fetchone()
        if date2_data is None:
            # 对于新用户的更新逻辑
            resp = await get_data(region_id, account_id, ac)
            now_time = now_iso()
            key = f"metrics:http:{now_time[:10]}:{region}_total"
            if region_id == 4:
                redis_client.incrby(key, 7)
            else:
                redis_client.incrby(key, 5)
            error_count, error_return = varify_responses(resp)
            if error_count != None:
                key = f"metrics:http:{now_time[:10]}:{region}_error"
                redis_client.incrby(key, error_count)
                return error_return
            user_basic = resp[0]
            update_base(region_id, account_id, user_basic)
            if user_basic:
                user_basic = user_basic[str(account_id)]
            if 'hidden_profile' in user_basic:
                # 用户隐藏战绩
                cursor.execute("""
                    INSERT INTO user (
                        date,is_public,leveling_points,
                        karma,win_rate,avg_damage,
                        avg_frags,cache
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?
                    );
                """,[date_2,0,0,0,0,0,0,None])
                cursor.execute("""
                    INSERT INTO user (
                        date,is_public,leveling_points,
                        karma,win_rate,avg_damage,
                        avg_frags,cache
                    ) VALUES (
                        ?,?,?,?,?,?,?,?,?
                    );
                """,[date_1,0,0,0,0,0,0,None])
                conn.commit()
                return 'HiddenProfile'
            elif (
                user_basic == None or
                'statistics' not in user_basic or 
                'basic' not in user_basic['statistics'] or 
                user_basic['statistics']['basic']['leveling_points'] == 0
            ):
                # 用户数据不存在删除recent
                del_recent(region_id, account_id)
                return 'DeleteRecent'
            else:
                lbt = user_basic['statistics']['basic']['last_battle_time']
                if int(time.time()) - lbt >= 360*24*60*60:
                    # 用户长期不活跃删除recent
                    del_recent(region_id, account_id)
                    return 'DeleteRecent'
                leveling_points = user_basic['statistics']['basic']['leveling_points']
                karma = user_basic['statistics']['basic']['karma']
                if user_basic['statistics']['pvp'] == {}:
                    win_rate = 0
                    avg_damage = 0
                    avg_frags = 0
                else:
                    pvp_count = user_basic['statistics']['pvp']['battles_count']
                    win_rate = round(user_basic['statistics']['pvp']['wins']/pvp_count*100,4)
                    avg_damage = round(user_basic['statistics']['pvp']['damage_dealt']/pvp_count,4)
                    avg_frags = round(user_basic['statistics']['pvp']['frags']/pvp_count,4)
                if region_id == 4:
                    battle_dict, statis_dict = responeses_processing([
                        resp[1][str(account_id)]['statistics'],
                        resp[2][str(account_id)]['statistics'],
                        resp[3][str(account_id)]['statistics'],
                        resp[4][str(account_id)]['statistics'],
                        resp[5][str(account_id)]['statistics'],
                        resp[6][str(account_id)]['statistics']
                    ])
                else:
                    battle_dict, statis_dict = responeses_processing([
                        resp[1][str(account_id)]['statistics'],
                        resp[2][str(account_id)]['statistics'],
                        resp[3][str(account_id)]['statistics'],
                        resp[4][str(account_id)]['statistics']
                    ])
                user_cache = {}
                ships_cache = []
                for ship_id, ship_battles in battle_dict.items():
                    if ship_battles > 0:
                        user_cache[ship_id] = [ship_battles, int(date_2)]
                        ships_cache.append([ship_id,date_2,json.dumps(statis_dict[ship_id],separators=(",", ":"))])
                user_cache = json.dumps(user_cache,separators=(",", ":"))
                cursor.execute("""
                    INSERT INTO user (
                        date,is_public,leveling_points,
                        karma,win_rate,avg_damage,
                        avg_frags,cache
                    ) VALUES (
                        ?,?,?,?,?,?,?,?
                    );
                """,[date_2,1,leveling_points,karma,win_rate,avg_damage,avg_frags,user_cache])
                cursor.execute("""
                    INSERT INTO user (
                        date,is_public,leveling_points,
                        karma,win_rate,avg_damage,
                        avg_frags,cache
                    ) VALUES (
                        ?,?,?,?,?,?,?,?
                    );
                """,[date_1,1,leveling_points,karma,win_rate,avg_damage,avg_frags,user_cache])
                for ship_cache in ships_cache:
                    cursor.execute("""
                        INSERT OR REPLACE INTO ships (
                            ship_id,
                            date,
                            cache
                        ) VALUES (
                            ?, ?, ?
                        );
                    """, ship_cache)
                conn.commit()
                return 'NewAccount'
        else:
            cursor.execute("""
                SELECT 
                    is_public, 
                    leveling_points, 
                    karma, 
                    win_rate, 
                    avg_damage, 
                    avg_frags, 
                    cache
                FROM user
                WHERE date = ?;
            """, [date_1])
            date1_data = cursor.fetchone()
            if date1_data is None:
                # 今日日期下没有数据条目，先复制昨日数据条目
                cursor.execute("""
                    INSERT INTO user (
                        date,is_public,leveling_points,
                        karma,win_rate,avg_damage,
                        avg_frags,cache
                    ) VALUES (
                        ?,?,?,?,?,?,?,?
                    );
                """,[date_1,date2_data[0],date2_data[1],date2_data[2],date2_data[3],date2_data[4],date2_data[5],date2_data[6]])
                conn.commit()
                return 'CopyFile'
            else:
                if date1_data[1] == total_battles:
                    return 'NoChanaged'
                # 用户有数据的情况下，数据不一致，有新增数据
                resp = await get_data(region_id, account_id, ac)
                now_time = now_iso()
                key = f"metrics:http:{now_time[:10]}:{region}_total"
                if region_id == 4:
                    redis_client.incrby(key, 7)
                else:
                    redis_client.incrby(key, 5)
                error_count, error_return = varify_responses(resp)
                if error_count != None:
                    key = f"metrics:http:{now_time[:10]}:{region}_error"
                    redis_client.incrby(key, error_count)
                    return error_return
                user_basic = resp[0]
                if user_basic:
                    user_basic = user_basic[str(account_id)]
                if 'hidden_profile' in user_basic:
                    # 用户隐藏战绩
                    cursor.execute("""
                        REPLACE INTO user (
                            date,is_public,leveling_points,
                            karma,win_rate,avg_damage,
                            avg_frags,cache
                        ) VALUES (
                            ?,?,?,?,?,?,?,?,?
                        );
                    """,[date_1,0,0,0,0,0,0,None])
                    if enable_daily:
                        del_recents(region_id, account_id)
                    conn.commit()
                    return 'HiddenProfile'
                elif (
                    user_basic == None or
                    'statistics' not in user_basic or 
                    'basic' not in user_basic['statistics'] or 
                    user_basic['statistics']['basic']['leveling_points'] == 0
                ):
                    # 用户数据不存在删除recent
                    del_recent(region_id, account_id)
                    if enable_daily:
                        del_recents(region_id, account_id)
                    return 'DeleteRecent'
                else:
                    lbt = user_basic['statistics']['basic']['last_battle_time']
                    if enable_daily and (int(time.time()) - lbt >= 90*24*60*60):
                        del_recents(region_id, account_id)
                        enable_daily = 0
                    if int(time.time()) - lbt >= 360*24*60*60:
                        # 用户长期不活跃删除recent
                        del_recent(region_id, account_id)
                        return 'DeleteRecent'
                    leveling_points = user_basic['statistics']['basic']['leveling_points']
                    karma = user_basic['statistics']['basic']['karma']
                    if user_basic['statistics']['pvp'] == {}:
                        win_rate = 0
                        avg_damage = 0
                        avg_frags = 0
                    else:
                        pvp_count = user_basic['statistics']['pvp']['battles_count']
                        win_rate = round(user_basic['statistics']['pvp']['wins']/pvp_count*100,4)
                        avg_damage = round(user_basic['statistics']['pvp']['damage_dealt']/pvp_count,4)
                        avg_frags = round(user_basic['statistics']['pvp']['frags']/pvp_count,4)
                    battle_dict, statis_dict = responeses_processing([
                        resp[1][str(account_id)]['statistics'],
                        resp[2][str(account_id)]['statistics'],
                        resp[3][str(account_id)]['statistics'],
                        resp[4][str(account_id)]['statistics']
                    ])
                    if date1_data[0] == 0 or date1_data[6] == None:
                        user_cache = {}
                        ships_cache = []
                        for ship_id, ship_battles in battle_dict.items():
                            if ship_battles > 0:
                                user_cache[ship_id] = [ship_battles, int(date_1)]
                                ships_cache.append([ship_id,date_1,json.dumps(statis_dict[ship_id],separators=(",", ":"))])
                        user_cache = json.dumps(user_cache,separators=(",", ":"))
                        cursor.execute("""
                            INSERT INTO user (
                                date,is_public,leveling_points,
                                karma,win_rate,avg_damage,
                                avg_frags,cache
                            ) VALUES (
                                ?,?,?,?,?,?,?,?
                            );
                        """,[date_1,1,leveling_points,karma,win_rate,avg_damage,avg_frags,user_cache])
                        for ship_cache in ships_cache:
                            cursor.execute("""
                                INSERT OR REPLACE INTO ships (
                                    ship_id,
                                    date,
                                    cache
                                ) VALUES (
                                    ?, ?, ?
                                );
                            """, ship_cache)
                        conn.commit()
                        return 'FullUpdate'
                    else:
                        # 更新有变更船只数据的索引
                        diff_ship_ids = []
                        old_battles = json.loads(date1_data[6])
                        for ship_id, ship_battles in battle_dict.items():
                            if ship_battles > 0:
                                if ship_id not in old_battles:
                                    diff_ship_ids.append([ship_id, None])
                                    old_battles[ship_id] = [ship_battles, int(date_1)]
                                if ship_battles != old_battles[ship_id][0]:
                                    diff_ship_ids.append([ship_id, str(old_battles[ship_id][1])])
                                    old_battles[ship_id] = [ship_battles, int(date_1)]
                        # 对于启用recents用户计算数据
                        if enable_daily:
                            recents_data = {}
                            redis_key = f"recent:{region_id}:{account_id}:{int(time.time())}"
                            for ship_id, ship_refer in diff_ship_ids:
                                if ship_refer == None:
                                    old_data = [[],[],[],[]]
                                else:
                                    cursor.execute("""
                                        SELECT 
                                            cache 
                                        FROM ships 
                                        WHERE ship_id = ? 
                                          AND date = ?;
                                    """,[ship_id, ship_refer])
                                    old_data = json.loads(cursor.fetchone()[0])
                                temp_data = diff_lists(statis_dict[ship_id],old_data)
                                if temp_data:
                                    recents_data[ship_id] = temp_data
                            if recents_data:
                                redis_client.set(redis_key, json.dumps(recents_data), 7*24*60*60)
                        # 将新数据写入数据库
                        cursor.execute("""
                            REPLACE INTO user (
                                date,is_public,leveling_points,
                                karma,win_rate,avg_damage,
                                avg_frags,cache
                            ) VALUES (
                                ?,?,?,?,?,?,?,?
                            );
                        """,[date_1,1,leveling_points,karma,win_rate,avg_damage,avg_frags,json.dumps(old_battles,separators=(",", ":"))])
                        ships_cache = []
                        for ship_id in [x[0] for x in diff_ship_ids]:
                            ships_cache.append([ship_id,date_1,json.dumps(statis_dict[ship_id],separators=(",", ":"))])
                        for ship_cache in ships_cache:
                            cursor.execute("""
                                INSERT OR REPLACE INTO ships (
                                    ship_id,
                                    date,
                                    cache
                                ) VALUES (
                                    ?,?,?
                                );
                            """, ship_cache)
                        conn.commit()
                        return 'ChangedUpdate'
                        
                    
    except Exception as e:
        logger.error((f"{traceback.format_exc()}"))
        return type(e).__name__
    finally:
        conn.close()
    