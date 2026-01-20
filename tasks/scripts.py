import os
import time
import json
import pymysql
import requests
from typing import Dict
from datetime import datetime

from .exception import handle_program_exception_sync
from .middlewares import redis_client, db_pool
from celery.app.base import logger

VORTEX_API_ENDPOINTS = {
    1: 'https://vortex.worldofwarships.asia',
    2: 'https://vortex.worldofwarships.eu',
    3: 'https://vortex.worldofwarships.com',
    4: 'https://vortex.korabli.su',
    5: 'https://vortex.wowsgame.cn'
}

def get_insignias(data: dict):
        if data is None or data == {}:
            return None
        return f"{data['texture_id']}-{data['symbol_id']}-{data['border_color_id']}-{data['background_color_id']}-{data['background_id']}"

def get_activity_level(last_battle_time: int = 0):
        "获取activity_level"
        current_timestamp = int(time.time())
        time_differences = [
            (1 * 24 * 60 * 60, 2),
            (3 * 24 * 60 * 60, 3),
            (7 * 24 * 60 * 60, 4),
            (30 * 24 * 60 * 60, 5),
            (90 * 24 * 60 * 60, 6),
            (180 * 24 * 60 * 60, 7),
            (360 * 24 * 60 * 60, 8),
        ]
        time_since_last_battle = current_timestamp - last_battle_time
        for time_limit, return_value in time_differences:
            if time_since_last_battle <= time_limit:
                return return_value
        return 9

@handle_program_exception_sync
def refresh_user(user_id: dict):
    region_id = user_id['region_id']
    account_id = user_id['account_id']
    region_dict = {1: 'asia',2: 'eu',3: 'na',4: 'ru',5: 'cn'}
    region = region_dict[region_id]
    # metrics
    now_time = datetime.now().isoformat(timespec="seconds")
    redis_client.incr(f'metrics:celery:{now_time[0:10]}')
    # 先删除redis的key
    key = f"user_refresh:{region_id}:{account_id}"
    redis_client.delete(key)
    # 请求接口
    redis_key = f"token:ac:{account_id}"
    result = redis_client.get(redis_key)
    if result:
        result = json.loads(result)
        ac = result.get('ac')
    else:
        ac = None
    base_url = VORTEX_API_ENDPOINTS[region_id]
    url = f'{base_url}/api/accounts/{account_id}/' + (f'?ac={ac}' if ac else '')
    try:
        response = requests.get(url=url,timeout=3)
    except:
        key = f"metrics:http:{now_time[:10]}:{region}_total"
        redis_client.incr(key)
        key = f"metrics:http:{now_time[:10]}:{region}_error"
        redis_client.incr(key)
        logger.warning(f'NetworkError | {url}')
        return 'network error'
    
    key = f"metrics:http:{now_time[:10]}:{region}_total"
    redis_client.incr(key)
    status_code = response.status_code
    if status_code not in [200, 404]:
        key = f"metrics:http:{now_time[:10]}:{region}_error"
        redis_client.incr(key)
        logger.warning(msg=f'HTTP_{status_code} | {url}')
        return 'network error'
    user_data = {
        'is_enabled': 1,
        'activity_level': 0,
        'is_public': 1,
        'total_battles': 0,
        'pvp_battles': 0,
        'ranked_battles': 0,
        'last_battle_at': 0,
        'username': None,
        'register_time': None,
        'insignias': None
    }
    if status_code == 404:
        user_data['is_enabled'] = 0
    else:
        result: Dict[str, dict] = response.json()
        result = result.get('data').get(str(account_id))
        if 'hidden_profile' in result:
            user_data['is_public'] = 0
            user_data['username'] = result['name']
        elif (
            result == None or
            'statistics' not in result or 
            'basic' not in result['statistics'] or 
            result['statistics']['basic']['leveling_points'] == 0
        ):
            user_data['is_enabled'] = 0
            if 'name' in result:
                user_data['username'] = result['name']
        else:
            user_data['username'] = result['name']
            user_data['register_time'] = result['statistics']['basic']['created_at']
            user_data['insignias'] = get_insignias(result['dog_tag'])
            user_data['total_battles'] = result['statistics']['basic']['leveling_points']
            user_data['last_battle_at'] = result['statistics']['basic']['last_battle_time']
            user_data['pvp_battles'] = 0 if result['statistics']['pvp'] == {} else result['statistics']['pvp']['battles_count']
            if region_id == 4:
                ranked_count = 0
                ranked_count += 0 if result['statistics']['rank_solo'] == {} else result['statistics']['rank_solo']['battles_count']
                ranked_count += 0 if result['statistics']['rating_solo'] == {} else result['statistics']['rating_solo']['battles_count']
                ranked_count += 0 if result['statistics']['rating_div'] == {} else result['statistics']['rating_div']['battles_count']
                user_data['ranked_battles'] = ranked_count
            else:
                user_data['ranked_battles'] = 0 if result['statistics']['rank_solo'] == {} else result['statistics']['rank_solo']['battles_count']
            user_data['activity_level'] = get_activity_level(user_data['last_battle_at'])
    conn = db_pool.connection()
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            if user_data['username']:
                if user_data['register_time'] == None:
                    sql = """
                        UPDATE user_base 
                        SET 
                            username = %s, 
                            touch_at = CURRENT_TIMESTAMP 
                        WHERE region_id = %s 
                          AND account_id = %s;
                    """
                    cursor.execute(
                        sql,[user_data['username'], region_id, account_id]
                    )
                else:
                    sql = """
                        UPDATE user_base 
                        SET 
                            username = %s, 
                            register_time = FROM_UNIXTIME(%s), 
                            insignias = %s, 
                            touch_at = CURRENT_TIMESTAMP 
                        WHERE region_id = %s 
                          AND account_id = %s;
                    """
                    cursor.execute(
                        sql,[user_data['username'], user_data['register_time'], user_data['insignias'], region_id, account_id]
                    )
            if user_data['is_enabled'] == 0:
                sql = """
                    UPDATE user_stats 
                    SET 
                        is_enabled = %s, 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id = %s;
                """
                cursor.execute(
                    sql,
                    [
                        user_data['is_enabled'], account_id
                    ]
                )
            elif user_data['total_battles'] != 0:
                sql = """
                    UPDATE user_stats 
                    SET 
                        is_enabled = %s, 
                        activity_level = %s, 
                        is_public = %s, 
                        total_battles = %s, 
                        pvp_battles = %s, 
                        ranked_battles = %s, 
                        last_battle_at = FROM_UNIXTIME(%s), 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id = %s;
                """
                cursor.execute(
                    sql,
                    [
                        user_data['is_enabled'], user_data['activity_level'], user_data['is_public'], user_data['total_battles'],
                        user_data['pvp_battles'], user_data['ranked_battles'], user_data['last_battle_at'], account_id
                    ]
                )
            else:
                sql = """
                    UPDATE user_stats 
                    SET 
                        is_enabled = %s, 
                        activity_level = %s, 
                        is_public = %s, 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id = %s;
                """
                cursor.execute(
                    sql,
                    [
                        user_data['is_enabled'], user_data['activity_level'], user_data['is_public'], account_id
                    ]
                )
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()
    return 'ok'

# @handle_program_exception_sync
# def sum_recent(data: dict):
#     version = data['version']
#     region_id = str(data['region_id'])
#     recent_data = data['data']
#     file_path = os.path.join(RECENT_DATA_PATH, f'{version}.json')
#     if os.path.exists(file_path):
#         with open(file_path, 'r', encoding='utf-8') as f:
#             current_data = json.load(f)
#     else:
#         current_data = {'1':{},'2':{},'3':{},'4':{},'5':{}}
#     for ship_id, ship_data in recent_data.items():
#         del ship_data[1]
#         if ship_id not in current_data[region_id]:
#             current_data[region_id][ship_id] = ship_data
#         else:
#             current_data[region_id][ship_id] = [a + b for a, b in zip(ship_data, current_data[region_id][ship_id])]
#     with open(file_path, 'w', encoding='utf-8') as f:
#         json.dump(current_data, f, ensure_ascii=False)
#     return 'ok'