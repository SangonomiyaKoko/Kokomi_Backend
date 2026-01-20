#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import math
import pymysql
import traceback
from tqdm import tqdm

from logger import logger
from settings import CLIENT_NAME, REFRESH_INTERVAL
from middlewares import db_pool, redis_client
from utils import get_max_id, now_iso, decompress

def main():
    while True:
        # 设置一个key标记
        redis_client.set(f'status:{CLIENT_NAME}', 1, ex=REFRESH_INTERVAL+60)
        st = int(time.time())

        max_id = get_max_id()
        
        # 获取总计批次
        index = 1
        pbar = tqdm(total=max_id)
        try:
            while index <= max_id:
                conn = db_pool.connection()
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                try:
                    sql = """
                        SELECT 
                            b.region_id, 
                            b.account_id, 
                            c.cache 
                        FROM user_base AS b 
                        LEFT JOIN user_cache AS c 
                            ON b.account_id = c.account_id 
                        WHERE b.id = %s;
                    """
                    cursor.execute(sql,[index])
                    data = cursor.fetchone()
                    region_id = data['region_id']
                    account_id = data['account_id']
                    pbar.set_description(f"{now_iso()} | {region_id}-{account_id} Processing")
                    result = decompress(data['cache'])
                    tqdm.write(f"{now_iso()} | {region_id}-{account_id} {len(result) if result else 0}")
                    pbar.update(1)
                except Exception as e:
                    conn.rollback()
                    tqdm.write(f"{now_iso()} | {traceback.format_exc()}")
                    logger.error((f"{now_iso()} | {traceback.format_exc()}"))
                finally:
                    cursor.close()
                    conn.close()
                    index += 1
        finally:
            pbar.close()
                
        ct = int(time.time()) - st
        if ct < REFRESH_INTERVAL:
            print(f'{now_iso()} | The current update cycle is complete. Sleep for {int(REFRESH_INTERVAL-ct)} second.')
            time.sleep(REFRESH_INTERVAL-ct)

if __name__ == "__main__":
    print(f'{now_iso()} | Start running service {CLIENT_NAME}')
    try:
        main()
    except KeyboardInterrupt:
        print(f'{now_iso()} | Received process shutdown signal')
    wait_second = 1
    while wait_second > 0:
        print(f'{now_iso()} | Service will close after {wait_second} seconds')
        time.sleep(1)
        wait_second -= 1
    print(f'{now_iso()} | Service has been closed')