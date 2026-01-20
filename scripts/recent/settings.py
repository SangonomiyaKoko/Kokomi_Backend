import os
from dotenv import load_dotenv

load_dotenv()  # 读取当前工作目录下的 .env
cwd = os.getcwd()


CLIENT_NAME = 'Recent'
LOG_LEVEL = 'debug'
DATA_DIR = '/app/data'
LOG_DIR = '/app/logs'
REFRESH_INTERVAL = 60

MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USERNAME = os.getenv("MYSQL_USERNAME")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")

MAIN_DB = os.getenv("MAIN_DB")

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")