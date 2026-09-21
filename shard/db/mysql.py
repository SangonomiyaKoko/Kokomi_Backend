from typing import Any, Iterator
from contextlib import contextmanager

from pymysql import Connection
from pymysql.cursors import Cursor


class MySQLOPS:
    @staticmethod
    @contextmanager
    def read_only(conn: Connection) -> Iterator[Cursor]:
        """MySQL 上下文管理器，仅读取

        source 可以是 pymysql 的 Connection，也可以是 PooledDB 等连接池。
        出错时直接抛出，由调用方负责记录日志
        """
        with conn.cursor() as cur:
            yield cur

    @staticmethod
    @contextmanager
    def transaction(conn: Connection) -> Iterator[Cursor]:
        """MySQL 事务上下文管理器

        source 可以是 pymysql 的 Connection，也可以是 PooledDB 等连接池。
        出错时回滚并抛出，由调用方负责记录日志
        """
        try:
            with conn.cursor() as cur:
                yield cur
        except Exception:
            conn.rollback()
            raise
        else:
            conn.commit()
