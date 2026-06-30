import os
import logging
import pymysql
from pathlib import Path
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(os.getcwd())

# 加载环境变量
if (ROOT_DIR / 'env.dev').exists():
    logger.info('Loading environment file: env.dev')
    load_dotenv('env.dev')
elif (ROOT_DIR / 'env.prod').exists():
    logger.info('Loading environment file: env.prod')
    load_dotenv('env.prod')
else:
    raise FileNotFoundError('No environment file found')

DB_CONFIG = {
    "host": 'localhost',
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": 'root',
    "password": os.getenv("MYSQL_ROOT_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    'autocommit': False
}

sql = """
DROP TABLE IF EXISTS D_ship_type;
DROP TABLE IF EXISTS D_ship_rarity;
DROP TABLE IF EXISTS D_ship_nation;
DROP TABLE IF EXISTS D_clan_activity_strategy;
DROP TABLE IF EXISTS D_user_activity_strategy;
DROP FUNCTION IF EXISTS F_user_next_refresh_at;
DROP FUNCTION IF EXISTS F_clan_next_refresh_at;
"""

def main():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        with conn.cursor() as cursor:
            for stmt in statements:
                cursor.execute(stmt)

        conn.commit()
        logger.info("Execute successfully")
    except Exception:
        conn.rollback()
        logger.exception("Execute failed, rolled back")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    """执行 sql 语句
    
    使用示例：
    python tests/execute_sql.py
    """

    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")