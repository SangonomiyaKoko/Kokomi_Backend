import requests
import pymysql
from datetime import datetime

from logger import logger
from middlewares import db_pool, redis_client


CLAN_API_URL_LIST = {
    1: 'https://clans.worldofwarships.asia',
    2: 'https://clans.worldofwarships.eu',
    3: 'https://clans.worldofwarships.com',
    4: 'https://clans.korabli.su',
    5: 'https://clans.wowsgame.cn'
}

def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")

def get_max_id():
    # 先获取数据库中id最大值，确定循环上限
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        sql = """
            SELECT 
                MAX(id) AS max_id 
            FROM clan_base;
        """
        cursor.execute(sql)
        data = cursor.fetchone()
        return data['max_id']
    finally:
        cursor.close()
        conn.close()

def fetch_data(url):
    try:
        resp = requests.get(url)
        if resp.status_code == 200:
            result = resp.json()
            return result
        logger.warning(f'Code_{resp.status_code} {url}')
        return f'HTTP_STATUS_{resp.status_code}'
    except Exception as e:
        logger.warning(f"{type(e).__name__} {url}")
        return f'ERROR_{type(e).__name__}'
    
def varify_responses(responses: list | dict):
    error = 0
    error_return = None
    if type(responses) != dict:
        error += 1
        error_return = responses
    if error == 0:
        return None, None
    else:
        return error, error_return

def get_clan_users(region_id: int, clan_id: int):
    region_dict = {1: 'asia',2: 'eu',3: 'na',4: 'ru',5: 'cn'}
    region = region_dict[region_id]
    base_url = CLAN_API_URL_LIST.get(region_id)
    url = f'{base_url}/api/members/{clan_id}/'
    result = fetch_data(url)
    now_time = now_iso()
    key = f"metrics:http:{now_time[:10]}:{region}_total"
    redis_client.incrby(key, 3)
    error_count, error_return = varify_responses(result)
    if error_count != None:
        key = f"metrics:http:{now_time[:10]}:{region}_error"
        redis_client.incrby(key, error_count)
        return error_return
    return result