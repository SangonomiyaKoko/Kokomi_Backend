#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import asyncio
import json
import os
import pymysql
import traceback
import signal

from logger import logger
from settings import CLIENT_NAME, REFRESH_INTERVAL, BATCH_SIZE, DATA_DIR
from middlewares import redis_client, db_pool
from utils import get_max_id, get_version, get_cache_data, decompress, compress, get_update_list



async def main():
    while True:
        # 标记进程正常运行
        redis_client.set(f'status:{CLIENT_NAME}', 1, ex=REFRESH_INTERVAL+60)
        st = time.time()

        max_id = get_max_id()
        logger.info(f'MaxID: {max_id}')
        total_update, update_list = get_update_list(max_id, BATCH_SIZE)
        logger.info(f'Database traversal complete. {total_update} users need to be updated')
        versions = get_version()
        logger.info(f'ASIA: {versions[0]} | EU: {versions[1]} | NA: {versions[2]} | RU: {versions[3]} | CN: {versions[4]} ')
        i = 1
        for region_id in [1, 2, 3, 4, 5]:
            for account_id in update_list[region_id-1]:
                # 请求接口
                redis_key = f"token:ac:{account_id}"
                result = redis_client.get(redis_key)
                if result:
                    result = json.loads(result)
                    ac = result.get('ac')
                else:
                    ac = None
                old_data = None
                old_pvp = None
                cache_data = await get_cache_data(region_id, account_id, ac)
                if type(cache_data) == str:
                    logger.error(f'[{i}/{total_update}] {region_id}-{account_id} | {cache_data}')
                    i += 1
                    continue
                conn = db_pool.connection()
                cursor = conn.cursor(pymysql.cursors.DictCursor)
                try:
                    if cache_data == {}:
                        sql = """
                            UPDATE user_cache 
                            SET 
                                pvp_count = %s, 
                                win_rate = %s, 
                                avg_damage = %s, 
                                avg_frags = %s, 
                                max_damage = %s, 
                                max_damage_id = %s, 
                                max_exp = %s, 
                                max_exp_id = %s, 
                                cache = %s 
                            WHERE 
                                account_id = %s;
                        """
                        cursor.execute(
                            sql,[
                                0,
                                0,
                                0,
                                0,
                                0,
                                None,
                                0,
                                None,
                                None,
                                account_id
                            ]
                        )
                        logger.info(f'[{i}/{total_update}] {region_id}-{account_id} | NoData or Hidden')
                        i += 1
                        continue
                    else:
                        basic_data = cache_data['overall']
                        new_data = cache_data['data']
                        sql = """
                            SELECT 
                                pvp_count, 
                                cache 
                            FROM user_cache 
                            WHERE account_id = %s;
                        """
                        cursor.execute(sql,[account_id])
                        data = cursor.fetchone()
                        old_pvp = data['pvp_count']
                        old_data = decompress(data['cache'])
                        sql = """
                            UPDATE user_cache 
                            SET 
                                pvp_count = %s, 
                                win_rate = %s, 
                                avg_damage = %s, 
                                avg_frags = %s, 
                                max_damage = %s, 
                                max_damage_id = %s, 
                                max_exp = %s, 
                                max_exp_id = %s, 
                                cache = %s 
                            WHERE 
                                account_id = %s;
                        """
                        cursor.execute(
                            sql,[
                                basic_data['battles_count'],
                                basic_data['win_rate'],
                                basic_data['avg_damage'],
                                basic_data['avg_frags'],
                                basic_data['max_damage'],
                                basic_data['max_damage_id'],
                                basic_data['max_exp'],
                                basic_data['max_exp_id'],
                                compress(new_data),
                                account_id
                            ]
                        )
                except Exception as e:
                    conn.rollback()
                    logger.error((f"{traceback.format_exc()}"))
                finally:
                    cursor.close()
                    conn.commit()
                    conn.close()
                # 计算差值，统计近期数据
                if old_pvp != 0 and basic_data['battles_count'] != 0:
                    add_count = basic_data['battles_count'] - old_pvp
                    # 计算recent数据
                    recent = {}
                    for ship_id,ship_info in new_data.items():
                        if ship_id not in old_data:
                            recent[ship_id] = ship_info
                        else:
                            if ship_info[0] > old_data[ship_id][0]:
                                recent[ship_id] = [x - y for x, y in zip(ship_info, old_data[ship_id])]
                    # 读取当前数据
                    file_path = os.path.join(DATA_DIR, 'recent', str(region_id), f'{versions[region_id-1]}.json')
                    if os.path.exists(file_path):
                        with open(file_path, 'r', encoding='utf-8') as f:
                            current_data = json.load(f)
                    else:
                        current_data = {}
                    # 将recent进行累加
                    for ship_id, ship_data in recent.items():
                        del ship_data[1] # 删除solo_count
                        if ship_id not in current_data:
                            current_data[ship_id] = ship_data[:6]
                        else:
                            current_data[ship_id] = [a + b for a, b in zip(ship_data[:6], current_data[ship_id])]
                    with open(file_path, 'w', encoding='utf-8') as f:
                        json.dump(current_data, f, ensure_ascii=False)
                    logger.info(f'[{i}/{total_update}] {region_id}-{account_id} | Successful, {add_count} new data entries')
                else:
                    logger.info(f'[{i}/{total_update}] {region_id}-{account_id} | Successful, no new data added')
                i += 1

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