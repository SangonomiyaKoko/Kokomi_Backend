import pymysql
from middlewares import db_pool

from logger import logger


def get_refresh_time(activity_level: int, lbt: int, enable_recent: bool, enable_daily: bool):
    hour = 60*60
    day = 24*hour
    refresh_time_dict = {
        0: [5*day,  6*hour,   2*hour],
        1: [25*day, 12*hour,  2*hour],
        2: [1*day,  0.5*hour, 20*60],
        3: [2*day,  1*hour,   25*60],
        4: [3*day,  2*hour,   30*60],
        5: [5*day,  3*hour,   30*60],
        6: [7*day,  4*hour,   60*60],
        7: [15*day, 5*hour,   2*hour],
        8: [20*day, 6*hour,   2*hour],
        9: [30*day, 12*hour,  2*hour]
    }
    if enable_daily:
        if lbt < 60*60:
            return 5*60
        else:
            return refresh_time_dict[activity_level][2]
    elif enable_recent:
        return refresh_time_dict[activity_level][1]
    else:
        return refresh_time_dict[activity_level][0]

def get_max_id():
    # 先获取数据库中id最大值，确定循环上限
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        sql = """
            SELECT 
                MAX(id) AS max_id 
            FROM user_stats;
        """
        cursor.execute(sql)
        data = cursor.fetchone()
        return data['max_id']
    except:
        logger.error(f'Read max_id failed')
    finally:
        cursor.close()
        conn.close()

def get_recent_user():
    recent_user = set()
    recents_user = set()
    # 先获取数据库中id最大值，确定循环上限
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        sql = """
            SELECT 
                account_id, 
                enable_recent, 
                enable_daily 
            FROM recent;
        """
        cursor.execute(sql)
        datas = cursor.fetchall()
        for data in datas:
            if data['enable_recent'] == 1:
                recent_user.add(data['account_id'])
                if data['enable_daily'] == 1:
                    recents_user.add(data['account_id'])
    except:
        logger.error(f'Read recent_user failed')
    finally:
        cursor.close()
        conn.close()
    return recent_user, recents_user