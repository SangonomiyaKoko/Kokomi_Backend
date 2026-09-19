from contextlib import contextmanager
from typing import Any, Iterator

from pymysql import Connection
from pymysql.cursors import Cursor

from ..logger import logger


@contextmanager
def mysql_read_only(
    conn: Connection, desc: Any = None
) -> Iterator[Cursor]:
    """MySQL 上下文管理器，仅读取"""
    try:
        with conn.cursor() as cur:
            yield cur
    except Exception as e:
        error_name = type(e).__name__
        logger.error(
            '%sDatabase read error: %s'
            , f'{desc} | ' if desc else ''
            , error_name
        )
        raise

@contextmanager
def mysql_transaction(
    conn: Connection, desc: Any = None
) -> Iterator[Cursor]:
    """MySQL 事务上下文管理器"""
    try:
        with conn.cursor() as cur:
            yield cur
    except Exception as e:
        conn.rollback()
        error_name = type(e).__name__
        logger.error(
            '%sDatabase operation error: %s'
            , f'{desc} | ' if desc else ''
            , error_name
        )
        raise
    else:
        conn.commit()
