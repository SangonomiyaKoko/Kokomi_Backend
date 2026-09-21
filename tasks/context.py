import redis
import pymysql
import requests
from dataclasses import dataclass, field

from redis import Redis
from requests.sessions import Session
from dbutils.pooled_db import PooledDB

from .settings import (
    REDIS_CONFIG, 
    MYSQL_CONFIG, 
    SSL_CA_BUNDLE
)

@dataclass
class RunContext:
    """运行上下文"""
    session: Session = field(init=False)
    db_pool: PooledDB = field(init=False)
    lock_client: Redis = field(init=False)
    redis_client: Redis = field(init=False)

    def __post_init__(self) -> None:
        _session = requests.Session()
        if SSL_CA_BUNDLE:
            # 处理俄服接口证书效验问题
            _session.verify = SSL_CA_BUNDLE
        self.session = _session

        self.redis_client = redis.Redis(**REDIS_CONFIG)
        # 锁客户端不采用同一个 db
        lock_config = {**REDIS_CONFIG, 'db': REDIS_CONFIG['db'] + 1}
        self.lock_client = redis.Redis(**lock_config)

        self.db_pool = PooledDB(
            creator=pymysql,
            maxconnections=4,     # 最大连接数
            charset="utf8mb4",
            autocommit=False,     # 必须使用手动事务
            **MYSQL_CONFIG
        )