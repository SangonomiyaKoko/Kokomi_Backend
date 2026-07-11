import os
import json
import redis
import logging
import pymysql
from tqdm import tqdm
from pathlib import Path
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(os.getcwd())

if (ROOT_DIR / 'env.dev').exists():
    load_dotenv('env.dev')
elif (ROOT_DIR / 'env.prod').exists():
    load_dotenv('env.prod')
else:
    raise FileNotFoundError('No environment file found')

DB_CONFIG = {
    "host": 'localhost',
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "autocommit": False
}
REDIS_CONFIG = {
    "host": 'localhost',
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DATABASE", 0)),
    "password": os.getenv("REDIS_PASSWORD"),
    "decode_responses": True
}

file_path = ROOT_DIR / 'data/json/clan_season.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    SEASON_ID = data.get('id', 0)

def read_ship_data(cursor) -> dict:
    """加载船只排行榜基准数据

    从视图读取每艘船的最低场次要求和服务器场均指标，
    用于计算玩家 Rating 的基准值

    Args:
        cursor: 数据库游标

    Returns:
        字典，键为 ship_id，值为 [win_rate, avg_damage, avg_frags]
    """
    ship_info = {}
    sql = """
        SELECT 
            ship_id, 
            stats_battles, 
            win_rate, 
            avg_damage, 
            avg_frags
        FROM V_ship_ranking_stats;
    """
    cursor.execute(sql)
    rows = cursor.fetchall()
    for row in rows:
        if row[1] < 1000:
            ship_info[str(row[0])] = None
        else:
            ship_info[str(row[0])] = [row[2], row[3], row[4]]
    return ship_info

def read_clan_league(cursor) -> dict:
    sql = """
        SELECT 
            clan_id, 
            public_rating, 
            stage_battles, 
            stage_victories 
        FROM T_clan_stats
        WHERE season = %s;
    """
    cursor.execute(sql, [SEASON_ID])
    rows = cursor.fetchall()

    result = {}
    for row in rows:
        # Rating = 公开评分 + 晋级赛场次*0.1 + 晋级赛胜场*0.01
        result[row[0]] = round(row[1] + row[2] * 0.1 + row[3] * 0.01, 2)

    return result

def refresh_leaderboard_meta(cursor, leaderboard_rows: int) -> None:
    """更新 leaderboard_rows 的统计数据"""
    sql = """
        UPDATE T_table_meta 
        SET 
            metric_value = %s 
        WHERE metric_key = 'leaderboard_rows';
    """
    cursor.execute(sql, [leaderboard_rows])

def refresh_leaderboard_mysql(cursor, ship_id: int) -> int:
    """更新 MySQL 排行榜中指定船只的 rating 和指标评级"""

    update_sql = """
        UPDATE T_ship_pvp_leaderboard l
        JOIN T_ship_stats_by_battles s 
            ON l.ship_id = s.ship_id
        SET
            l.rating = F_calculate_ship_pr(
                l.win_rate, l.avg_damage, l.avg_frags,
                s.win_rate, s.avg_damage, s.avg_frags
            ),
            l.avg_damage_level = F_get_metric_level(3, l.avg_damage, s.avg_damage),
            l.avg_frags_level = F_get_metric_level(4, l.avg_frags, s.avg_frags),
            l.updated_at = NOW()
        WHERE l.ship_id = %s;
    """

    cursor.execute(update_sql, [ship_id])
    return cursor.rowcount if cursor.rowcount else 0

def clear_leaderboard_redis(redis_client) -> None:
    """删除 Redis 中所有的排行榜 key"""
    # 获取所有匹配的 key
    all_keys = redis_client.keys('leaderboard:ship:*')
    
    if not all_keys:
        return
    
    redis_client.delete(*all_keys)
    
def refresh_leaderboard_redis(cursor, redis_client, ship_id: int) -> None:
    """重新构建船只的缓存数据"""
    cursor.execute(
        """
        SELECT 
            account_id, 
            rating
        FROM T_ship_pvp_leaderboard
        WHERE ship_id = %s;
        """,
        [ship_id],
    )
    rows = cursor.fetchall()

    if rows:
        key = f"leaderboard:ship:{ship_id}"
        # 使用管道批量操作提高性能
        pipe = redis_client.pipeline()
        for acc, rating in rows:
            if rating >= 0:
                pipe.zadd(key, {str(acc): float(rating)})
        pipe.execute()

def main():
    conn = pymysql.connect(**DB_CONFIG)
    redis_client = redis.Redis(**REDIS_CONFIG)

    try:
        with conn.cursor() as cursor:
            # 刷新工会排行榜
            if SEASON_ID != 0:
                result = read_clan_league(cursor)

                key = 'leaderboard:clan'
                pipe = redis_client.pipeline()
                pipe.delete(key)
                if result:
                    pipe.zadd(key, {str(k): float(v) for k, v in result.items()})
                pipe.execute()

                logger.info('Clan leaderboard cache refreshed')


            # 刷新船只排行榜
            leaderboard_rows = 0
            ranking_ship_ids = []
            
            # 读取符合要求的船只id列表
            ship_data = read_ship_data(cursor)
            for ship_id, ship_data in ship_data.items():
                if ship_data:
                    ranking_ship_ids.append(ship_id)

            if not ranking_ship_ids:
                return
            
            # 清空 Redis 的缓存
            clear_leaderboard_redis(redis_client)

            # 更新 MySQL 排行榜数据
            with tqdm(total=len(ranking_ship_ids), desc=f"Refreshing ship leaderboard", unit="ship") as pbar:
                for ship_id in ranking_ship_ids:
                    try:
                        leaderboard_rows += refresh_leaderboard_mysql(cursor, ship_id)
                        # 每条船单独提交，避免长事务
                        conn.commit()
                    except Exception as e:
                        conn.rollback()
                        tqdm.write(f'Ship {ship_id} refresh failed: {type(e).__name__}')
                    pbar.update()
                    # 重构 Redis 的缓存
                    refresh_leaderboard_redis(cursor, redis_client, ship_id)
            
            # 记录 leaderboard_rows 数据
            try:
                refresh_leaderboard_meta(cursor, leaderboard_rows)
                conn.commit()
            except Exception as e:
                conn.rollback()
                tqdm.write(f'Refresh meta failed: {type(e).__name__}')

        logger.info('User leaderboard cache refreshed')
    finally:
        if conn:
            conn.close()
        if redis_client:
            redis_client.close()

    logger.info(f"Ranking list data refreshed successfully: {leaderboard_rows} rows")


if __name__ == '__main__':
    """刷新并重建船只排行榜缓存脚本

    运行前请确保所有子服务已停止运行，避免读取到异常数据或影响服务正常运行

    使用示例：
    python tools/ranking.py
    """
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")