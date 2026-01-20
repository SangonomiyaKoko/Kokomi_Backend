import time
import pymysql
import traceback
import signal

from logger import logger
from settings import CLIENT_NAME, REFRESH_INTERVAL
from middlewares import db_pool, redis_client
from utils import get_clan_users, get_max_id



def main():
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
                        region_id, 
                        clan_id 
                    FROM clan_base 
                    WHERE id = %s;
                """
                cursor.execute(sql, [index])
                data = cursor.fetchone()
                # 获取到空数据，直接进入下一个循环
                # 但理论上不会获取到
                if data is None:
                    logger.info(f'[{index}/{max_id}] | NoData')
                    continue
                region_id = data['region_id']
                clan_id = data['clan_id']
                result = get_clan_users(region_id, clan_id)
                if type(result) == str:
                    logger.error(f'[{index}/{max_id}] {region_id}-{clan_id} | {result}')
                    continue
                users = {}
                for user_info in result.get('items'):
                    users[user_info['id']] = user_info['name']
                # 当前工会内玩家id列表
                user_ids = list(users.keys())
                if len(user_ids) == 0:
                    logger.info(f'[{index}/{max_id}] {region_id}-{clan_id} | NoData')
                    continue
                placeholders = ",".join(["%s"] * len(user_ids))
                sql = f"""
                    SELECT account_id 
                    FROM user_clan 
                    WHERE account_id IN ({placeholders});
                """
                cursor.execute(sql, user_ids)
                existing_ids = {row['account_id'] for row in cursor.fetchall()}
                missing_ids = set(user_ids) - existing_ids
                # 写入数据库中不存在的用户
                for account_id in missing_ids:
                    sql = """
                        INSERT INTO user_base (
                            region_id, 
                            account_id, 
                            username
                        ) VALUES (
                            %s, %s, %s
                        );
                    """
                    cursor.execute(sql, [region_id, account_id, f'User_{account_id}'])
                    sql = """
                        INSERT INTO user_stats (
                            account_id
                        ) VALUES (
                            %s
                        );
                    """
                    cursor.execute(sql, [account_id])
                    sql = """
                        INSERT INTO user_clan (
                            account_id
                        ) VALUES (
                            %s
                        );
                    """
                    cursor.execute(sql, [account_id])
                    sql = """
                        INSERT INTO user_cache (
                            account_id
                        ) VALUES (
                            %s
                        );
                    """
                    cursor.execute(sql, [account_id])
                    sql = """
                        UPDATE user_base 
                        SET 
                            username = %s, 
                            touch_at = CURRENT_TIMESTAMP 
                        WHERE region_id = %s 
                        AND account_id = %s;
                    """
                    cursor.execute(sql,[users[account_id], region_id, account_id])
                    conn.commit()
                # 删除已不再工会内的用户
                sql = """
                    SELECT 
                        account_id 
                    FROM user_clan 
                    WHERE clan_id = %s;
                """
                cursor.execute(sql,[clan_id])
                for existing_clan_user in cursor.fetchall():
                    if existing_clan_user['account_id'] not in user_ids:
                        sql = """
                            UPDATE user_clan 
                            SET 
                                clan_id = NULL, 
                                touch_at = CURRENT_TIMESTAMP 
                            WHERE account_id = %s;
                        """
                        cursor.execute(sql,[existing_clan_user['account_id']])
                # 刷新工会内所有用户的记录
                sql = f"""
                    UPDATE user_clan 
                    SET 
                        clan_id = %s, 
                        touch_at = CURRENT_TIMESTAMP 
                    WHERE account_id IN ({placeholders});
                """
                cursor.execute(sql, [clan_id] + user_ids)
                conn.commit()
                logger.info(f'[{index}/{max_id}] {region_id}-{clan_id} | Members: {len(user_ids)}')
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
    main()