import os
import time
import logging
import pymysql
from pymysql.constants import CLIENT
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
    'autocommit': False
}
DATABASE = os.getenv("MYSQL_DATABASE")

def main():
    logger.warning("This action will clear the data in the database")
    logger.warning("Do not use this script in a production environment!")
    confirm = input(f"Are you sure you want to rebuild database '{DATABASE}'? (Y/N): ").strip().upper()
    if confirm.upper() != 'Y':
        logger.info("Operation cancelled by user")
        return
    logger.info("Starting to execute the database rebuild command")
    time.sleep(2)
    conn = pymysql.connect(
        **DB_CONFIG,
        client_flag=CLIENT.MULTI_STATEMENTS
    )
    cursor = conn.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS `{DATABASE}`;")
    cursor.execute(f"CREATE DATABASE `{DATABASE}`;")
    cursor.execute(f"USE `{DATABASE}`;")
    sql_files = [
        ROOT_DIR / "init/mysql/01-schemas/01-base.sql",
        ROOT_DIR / "init/mysql/01-schemas/02-user.sql",
        ROOT_DIR / "init/mysql/01-schemas/03-clan.sql",
        ROOT_DIR / "init/mysql/01-schemas/04-ship.sql",
        ROOT_DIR / "init/mysql/02-data/01-base.sql",
        ROOT_DIR / "init/mysql/03-views/01-base.sql",
        ROOT_DIR / "init/mysql/04-functions/01-base.sql"
    ]
    for sql_file in sql_files:
        with sql_file.open("r", encoding="utf-8") as f:
            sql = f.read()
            cursor.execute(sql)
        logger.info(f'Executed: {sql_file}')
    conn.commit()
    conn.close()
    logger.info(f'Success: {DATABASE}')

if __name__ == '__main__':
    """用于在数据库初始化，删除并重建数据库

    使用示例：
    python init/scripts/rebuild_db.py
    """
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")