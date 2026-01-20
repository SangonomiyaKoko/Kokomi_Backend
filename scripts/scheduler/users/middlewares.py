import pymysql
import redis
from dbutils.pooled_db import PooledDB

from logger import logger
from settings import (
    MYSQL_HOST, MYSQL_PORT, MYSQL_USERNAME, MYSQL_PASSWORD,
    REDIS_HOST, REDIS_PORT, REDIS_PASSWORD, MAIN_DB
)


try:
    redis_client = redis.Redis(
        host=REDIS_HOST,
        port=REDIS_PORT,
        db=0,
        password=REDIS_PASSWORD,
        decode_responses=True  # 返回 str 而不是 bytes
    )
except:
    logger.error('Redis initialization failed!')

try:
    db_pool = PooledDB(
        creator=pymysql,
        maxconnections=2,     # 最大连接数
        mincached=1,           # 初始化时创建的连接
        maxcached=1,           # 池中最大空闲连接
        blocking=True,         # 连接用完是否阻塞
        host=MYSQL_HOST,
        port=MYSQL_PORT,
        user=MYSQL_USERNAME,
        password=MYSQL_PASSWORD,
        charset="utf8mb4",
        autocommit=False,
        database=MAIN_DB
    )
except:
    logger.error('MySQL initialization failed!')