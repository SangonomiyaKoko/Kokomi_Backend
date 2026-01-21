#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import time
import signal
import traceback

from logger import logger
from settings import CLIENT_NAME, REFRESH_INTERVAL
from middlewares import redis_client
from utils import get_clan_rank_data, check_clan_stats, get_clan_cvc_data, update_clan_season, is_cb_active

def main():
    while True:
        # 设置一个key标记程序正在运行
        redis_client.set(f'status:{CLIENT_NAME}', 1, ex=REFRESH_INTERVAL+60)
        st = time.time() # 程序开始运行时间，计算后续休眠时间
        if is_cb_active == True:
            total_clan_ids = []
            region_name_list = {1: 'Asia',2: 'Eu',3: 'Na',4: 'Ru',5: 'Cn'}
            # 俄服不计入
            for region_id in [1,2,3,5]:
                region_list = get_clan_rank_data(region_id)
                logger.info(f'{region_name_list[region_id]} Clan: {len(region_list)}')
                total_clan_ids = total_clan_ids + region_list
            logger.info(f'Total Clan: {len(total_clan_ids)}')
            update_ids = check_clan_stats(total_clan_ids)
            len_update_ids = len(update_ids)
            logger.info(f'Update Numbers: {len_update_ids}')
            i = 1
            for clan_info in update_ids:
                region_id = clan_info[0]
                clan_id = clan_info[1]
                result = get_clan_cvc_data(region_id, clan_id)
                if type(result) == str:
                    logger.error(f'[{i}/{len_update_ids}] {region_id}-{clan_id} | {result}')
                    continue
                update_result = update_clan_season(result)
                logger.info(f'[{i}/{len_update_ids}] {region_id}-{clan_id} | {update_result}')
                i += 1
        else:
            logger.info(f'Update time not yet reached')
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