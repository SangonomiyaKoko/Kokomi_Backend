#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import json
import signal
import asyncio
import pymysql
import traceback

from logger import logger
from settings import CLIENT_NAME, REFRESH_INTERVAL
from middlewares import db_pool, redis_client
from utils import get_max_id
from update import update

async def main():
    while True:
        # 设置一个key标记
        redis_client.set(f'status:{CLIENT_NAME}', 1, ex=REFRESH_INTERVAL+60)
        st = time.time()

        max_id = get_max_id()
        logger.info(f'MaxID: {max_id}')
        index = 1
        while index <= max_id:
            conn = db_pool.connection()
            cursor = conn.cursor(pymysql.cursors.DictCursor)
            try:
                sql = """
                    SELECT 
                        r.region_id, 
                        r.account_id,  
                        r.enable_recent, 
                        r.enable_daily, 
                        s.total_battles 
                    FROM recent AS r 
                    LEFT JOIN user_stats AS s 
                        ON r.account_id = s.account_id 
                    WHERE r.id = %s;
                """
                cursor.execute(sql,[index])
                data = cursor.fetchone()
                if data is None:
                    logger.info(f'[{index}/{max_id}] | NoData')
                    continue
                region_id = data['region_id']
                account_id = data['account_id']
                if data['enable_recent'] == 1:
                    redis_key = f"token:ac:{account_id}"
                    result = redis_client.get(redis_key)
                    if result:
                        result = json.loads(result)
                        ac = result.get('ac')
                    else:
                        ac = None
                    result = await update(
                        region_id=region_id,
                        account_id=account_id,
                        enable_daily=data['enable_daily'],
                        total_battles=data['total_battles'],
                        ac=ac
                    )
                    logger.info(f"[{index}/{max_id}] {region_id}-{account_id} | {result}")
            except Exception as e:
                conn.rollback()
                logger.error((f"{traceback.format_exc()}"))
            finally:
                index += 1
                cursor.close()
                conn.close()
                
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
    asyncio.run(main())