import json
import gzip
import time
import traceback
import pymysql
import asyncio
import httpx
from datetime import datetime
from middlewares import db_pool, redis_client
from logger import logger


VORTEX_API_URL_LIST = {
    1: 'https://vortex.worldofwarships.asia',
    2: 'https://vortex.worldofwarships.eu',
    3: 'https://vortex.worldofwarships.com',
    4: 'https://vortex.korabli.su',
    5: 'https://vortex.wowsgame.cn'
}

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def compress(data: dict):
    # 数据压缩
    if data:
        json_str = json.dumps(
            data,
            ensure_ascii=False,
            separators=(",", ":")  # 去空格，减小体积
        )
        json_bytes = json_str.encode("utf-8")
        return gzip.compress(json_bytes)
    else:
        return None

def decompress(gzip_bytes: bytes):
    # 数据解压
    if gzip_bytes:
        decompressed = gzip.decompress(gzip_bytes)
        return json.loads(decompressed)
    else:
        return None

def get_max_id():
    # 先获取数据库中id最大值，确定循环上限
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        sql = f"""
            SELECT 
                MAX(id) AS max_id 
            FROM user_stats;
        """
        cursor.execute(sql)
        data = cursor.fetchone()
        return data['max_id']
    finally:
        cursor.close()
        conn.close()

def get_version():
    # 先获取数据库中的游戏版本
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        sql = f"""
            SELECT 
                region_id,
                short_version
            FROM region_version;
        """
        cursor.execute(sql)
        data = cursor.fetchall()
        return [
            data[0]['short_version'],
            data[1]['short_version'],
            data[2]['short_version'],
            data[3]['short_version'],
            data[4]['short_version']
        ]
    finally:
        cursor.close()
        conn.close()

def get_update_list(max_id: int, batch_size: int):
    # 从数据库中批量读取并判断那些用户需要更新
    total_update = 0
    update_list = [[],[],[],[],[]]
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        for offset in range(0, max_id, batch_size):
            sql = """
                SELECT 
                    b.region_id, 
                    b.account_id, 
                    s.pvp_battles, 
                    c.pvp_count 
                FROM user_base AS b 
                LEFT JOIN user_stats AS s 
                    ON b.account_id = s.account_id 
                LEFT JOIN user_cache AS c 
                    ON b.account_id = c.account_id 
                WHERE b.id BETWEEN %s AND %s;
            """
            cursor.execute(sql, [offset+1, offset+batch_size])
            data = cursor.fetchall()
            for user_info in data:
                if user_info['pvp_battles'] != user_info['pvp_count']:
                    update_list[user_info['region_id']-1].append(user_info['account_id'])
                    total_update += 1
    except Exception as e:
        logger.error((f"{traceback.format_exc()}"))
    finally:
        cursor.close()
        conn.close()
    return total_update, update_list

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
    
def varify_responses(responses: list | dict):
    error = 0
    error_return = None
    for response in responses:
        if type(response) != dict:
            error += 1
            error_return = response
    if error == 0:
        return None, None
    else:
        return error, error_return

async def get_cache_data(
    region_id: int,
    account_id: int,
    ac_value: str = None
):
    api_url = VORTEX_API_URL_LIST.get(region_id)
    region_dict = {1: 'asia',2: 'eu',3: 'na',4: 'ru',5: 'cn'}
    region = region_dict[region_id]
    urls = [
        f'{api_url}/api/accounts/{account_id}/' + (f'?ac={ac_value}' if ac_value else ''),
        f'{api_url}/api/accounts/{account_id}/ships/' + (f'?ac={ac_value}' if ac_value else ''),
        f'{api_url}/api/accounts/{account_id}/ships/pvp/' + (f'?ac={ac_value}' if ac_value else '')
    ]
    tasks = []
    responses = []
    async with asyncio.Semaphore(len(urls)):
        for url in urls:
            tasks.append(fetch_data(url))
        responses = await asyncio.gather(*tasks)
    now_time = now_iso()
    key = f"metrics:http:{now_time[:10]}:{region}_total"
    redis_client.incrby(key, 3)
    error_count, error_return = varify_responses(responses)
    if error_count != None:
        key = f"metrics:http:{now_time[:10]}:{region}_error"
        redis_client.incrby(key, error_count)
        return error_return
    result = {}
    overall = {}
    basic_data = responses[0]
    update_base(region_id, account_id, basic_data)
    if basic_data:
            basic_data = basic_data[str(account_id)]
    if 'hidden_profile' in basic_data:
        return {}
    if (
        basic_data == None or basic_data == {} or
        'statistics' not in basic_data or 
        'basic' not in basic_data['statistics'] or 
        basic_data['statistics']['basic']['leveling_points'] == 0
    ):
        return {}
    pvp_count = basic_data['statistics']['pvp'].get('battles_count')
    if pvp_count and pvp_count > 0:
        overall = {
            'battles_count': pvp_count,
            'win_rate': round(basic_data['statistics']['pvp']['wins']/pvp_count*100,4),
            'avg_damage': round(basic_data['statistics']['pvp']['damage_dealt']/pvp_count,4),
            'avg_frags': round(basic_data['statistics']['pvp']['frags']/pvp_count,4),
            'max_damage': basic_data['statistics']['pvp']['max_damage_dealt'],
            'max_damage_id': basic_data['statistics']['pvp']['max_damage_dealt_vehicle'],
            'max_exp': basic_data['statistics']['pvp']['max_exp'],
            'max_exp_id': basic_data['statistics']['pvp']['max_exp_vehicle']
        }
    else:
        overall = {
            'battles_count': 0,
            'win_rate': 0,
            'avg_damage': 0,
            'avg_frags': 0,
            'max_damage': 0,
            'max_damage_id': 0,
            'max_exp': 0,
            'max_exp_id': 0
        }
    ships_data = responses[1]
    pvp_data = responses[2][str(account_id)]['statistics']
    for ship_id, ship_data in pvp_data.items():
        ship_data = pvp_data[str(ship_id)]['pvp']
        if ship_data == {}:
            continue
        solo_data = ships_data[str(account_id)]['statistics'][ship_id]
        if 'pvp_solo' in solo_data and solo_data['pvp_solo'] != {}:
            solo_count = solo_data['pvp_solo']['battles_count']
        else:
            solo_count = 0
        result[ship_id]=[
                ship_data['battles_count'],
                solo_count,
                ship_data['wins'],
                ship_data['damage_dealt'],
                ship_data['frags'],
                ship_data['original_exp'],
                ship_data['survived'],
                ship_data['max_exp'],
                ship_data['max_damage_dealt'],
                ship_data['max_frags']
            ]
    if pvp_count <= 0:
        return {}
    else:
        return {'overall':overall, 'data':result}
    

def get_activity_level(is_public: bool, total_battles: int = 0, last_battle_time: int = 0):
        "获取activity_level"
        if not is_public:
            return 0
        if total_battles == 0 or last_battle_time == 0:
            return 1
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

def get_insignias(data: dict):
    if data is None or data == {}:
        return None
    else:
        return f"{data['texture_id']}-{data['symbol_id']}-{data['border_color_id']}-{data['background_color_id']}-{data['background_id']}"

def update_base(region_id: int ,account_id: int, user_basic: dict):
    refresh_data = {
        'is_enabled': 0,
        'activity_level': 0,
        'is_public': 0,
        'username': "",
        'register_time': None,
        'insignias': None,
        'total_battles': 0,
        'pvp_battles': 0,
        'ranked_battles': 0,
        'last_battle_at': 0
    }
    if user_basic:
            user_basic = user_basic[str(account_id)]
    if 'hidden_profile' in user_basic:
        refresh_data['is_enabled'] = 1
        refresh_data['is_public'] = 0
        refresh_data['activity_level'] = get_activity_level(is_public=0)
        refresh_data['username'] = user_basic['name']
    elif (
        user_basic == None or user_basic == {} or
        'statistics' not in user_basic or 
        'basic' not in user_basic['statistics'] or 
        user_basic['statistics']['basic']['leveling_points'] == 0
    ):
        refresh_data['is_enabled'] = 0
    else:
        refresh_data['is_enabled'] = 1
        refresh_data['is_public'] = 1
        refresh_data['activity_level'] = get_activity_level(
            is_public=1,
            total_battles=user_basic['statistics']['basic']['leveling_points'],
            last_battle_time=user_basic['statistics']['basic']['last_battle_time']
        )
        if region_id == 4:
            ranked_count = 0
            ranked_count += 0 if user_basic['statistics']['rank_solo'] == {} else user_basic['statistics']['rank_solo']['battles_count']
            ranked_count += 0 if user_basic['statistics']['rating_solo'] == {} else user_basic['statistics']['rating_solo']['battles_count']
            ranked_count += 0 if user_basic['statistics']['rating_div'] == {} else user_basic['statistics']['rating_div']['battles_count']
        else:
            ranked_count = 0 if user_basic['statistics']['rank_solo'] == {} else user_basic['statistics']['rank_solo']['battles_count']
        refresh_data['username'] = user_basic['name']
        refresh_data['register_time'] = user_basic['statistics']['basic']['created_at']
        refresh_data['insignias'] = get_insignias(user_basic['dog_tag'])
        refresh_data['total_battles'] = user_basic['statistics']['basic']['leveling_points']
        refresh_data['pvp_battles'] = 0 if user_basic['statistics']['pvp'] == {} else user_basic['statistics']['pvp']['battles_count']
        refresh_data['ranked_battles'] = ranked_count
        refresh_data['last_battle_at'] = user_basic['statistics']['basic']['last_battle_time']
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        sql = """
            SELECT 
                username, 
                UNIX_TIMESTAMP(register_time) AS register_time, 
                insignias 
            FROM user_base 
            WHERE region_id = %s 
                AND account_id = %s;
        """
        cursor.execute(sql, [region_id, account_id])
        result = cursor.fetchone()
        if refresh_data['is_enabled'] == 0:
            sql = """
                UPDATE user_stats 
                SET 
                    is_enabled = %s, 
                    touch_at = CURRENT_TIMESTAMP 
                WHERE account_id = %s;
            """
            cursor.execute(sql, [refresh_data['is_enabled'], account_id])
        elif refresh_data['is_public'] == 0:
            sql = """
                UPDATE user_base 
                SET 
                    username = %s, 
                    touch_at = CURRENT_TIMESTAMP 
                WHERE region_id = %s 
                    AND account_id = %s;
            """
            cursor.execute(sql, [refresh_data['username'], region_id, account_id])
            sql = """
                UPDATE user_stats 
                SET 
                    is_enabled = %s, 
                    activity_level = %s, 
                    is_public = %s, 
                    touch_at = CURRENT_TIMESTAMP 
                WHERE account_id = %s;
            """
            cursor.execute(sql, [refresh_data['is_enabled'], refresh_data['activity_level'], refresh_data['is_public'], region_id, account_id])
        else:
            if (
                result['username'] != refresh_data['username'] or
                result['register_time'] != refresh_data['register_time'] or
                result['insignias'] != refresh_data['insignias']
            ):
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
                cursor.execute(sql, [refresh_data['username'],refresh_data['register_time'],refresh_data['insignias'],region_id,account_id])
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
            cursor.execute(sql, [
                refresh_data['is_enabled'],refresh_data['activity_level'],refresh_data['is_public'],
                refresh_data['total_battles'],refresh_data['pvp_battles'],refresh_data['ranked_battles'],
                refresh_data['last_battle_at'],account_id
            ])
        conn.commit()
    except Exception as e:
        conn.rollback()
        logger.error((f"{traceback.format_exc()}"))
    finally:
        cursor.close()
        conn.close()