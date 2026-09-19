from typing import Iterator
from contextlib import contextmanager

from pymysql.cursors import Cursor
from dbutils.pooled_db import PooledDB


@contextmanager
def mysql_transaction(
    db_pool: PooledDB
) -> Iterator[Cursor]:
    """MySQL 事务上下文管理器"""
    with db_pool.connection() as conn:
        try:
            with conn.cursor() as cursor:
                yield cursor
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
