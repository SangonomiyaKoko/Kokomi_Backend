#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import signal
import pymysql
import traceback

from logger import logger
from settings import CLIENT_NAME, REFRESH_INTERVAL, BATCH_SIZE
from middlewares import db_pool, redis_client, celery_app
from utils import get_refresh_time, get_max_id, get_recent_user


def main():
    while True:
        # 设置一个key标记程序正在运行
        redis_client.set(f'status:{CLIENT_NAME}', 1, ex=REFRESH_INTERVAL+60)
        st = time.time() # 程序开始运行时间，计算后续休眠时间

        send_tasks = 0
        max_id = get_max_id()
        recent, recents = get_recent_user()
        logger.info(f'MaxID: {max_id} | RecentUser: {len(recent)} | RecentsUser: {len(recents)}')
        conn = db_pool.connection()
        cursor = conn.cursor(pymysql.cursors.DictCursor)
        try:
            for offset in range(0, max_id, BATCH_SIZE):
                sql = """
                    SELECT 
                        b.region_id, 
                        b.account_id, 
                        s.activity_level, 
                        UNIX_TIMESTAMP(s.last_battle_at) AS last_battle_at, 
                        UNIX_TIMESTAMP(s.touch_at) AS touch_at 
                    FROM user_base AS b 
                    LEFT JOIN user_stats AS s 
                        ON b.account_id = s.account_id 
                    WHERE b.id BETWEEN %s AND %s;
                """
                cursor.execute(sql, [offset+1, offset+BATCH_SIZE])
                data = cursor.fetchall()
                for user in data:
                    region_id = user['region_id']
                    account_id = user['account_id']
                    enable_recent = True if account_id in recent else False
                    enable_daily = True if account_id in recents else False
                    now_time = int(time.time())
                    touch_time = user['touch_at'] if user['touch_at'] else 0
                    last_battle_time = user['last_battle_at'] if user['last_battle_at'] else 0
                    next_refresh_time = get_refresh_time(
                        user['activity_level'], 
                        now_time - last_battle_time, 
                        enable_recent, 
                        enable_daily
                    ) + touch_time
                    if next_refresh_time <= now_time:
                        # 需要更新
                        key = f"user_refresh:{region_id}:{account_id}"
                        # 通过redis去重
                        result = redis_client.set(key, 1, nx=True, ex=3600)
                        if result:
                            # 用户ID未重复，发送至任务队列
                            celery_app.send_task(
                                name='user_refresh', 
                                args=[{'region_id': region_id, 'account_id': account_id}], 
                                queue='refresh_queue'
                            )
                            send_tasks += 1
        except:
            logger.error(f'{traceback.format_exc()}')
        finally:
            cursor.close()
            conn.close()
        logger.info(f'This loop is complete. Send {send_tasks} tasks.')
        ct = time.time() - st
        if ct < REFRESH_INTERVAL:
            logger.info(f'This loop took {round(ct,2)} seconds')
            logger.info(f'The process sleeps for {round(REFRESH_INTERVAL-ct,2)} seconds')
            logger.info('-'*70)
            time.sleep(REFRESH_INTERVAL-ct)

def handler(signum, frame):
    logger.info('The process is closing')
    exit(0)

if __name__ == "__main__":
    logger.info(f'Start running service {CLIENT_NAME}')
    signal.signal(signal.SIGTERM, handler)
    main()