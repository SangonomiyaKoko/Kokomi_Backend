import random
from contextlib import contextmanager
from typing import Iterator

from pymysql import Connection
from pymysql.cursors import Cursor

from loggers import logger
from models import UserStats, UserRecord

@contextmanager
def mysql_transaction(conn: Connection, account_id: int) -> Iterator[Cursor]:
    """MySQL 事务上下文管理器"""
    try:
        with conn.cursor() as cur:
            yield cur
    except Exception as e:
        conn.rollback()
        error_name = type(e).__name__
        logger.error(f'{account_id} | Database operation error: {error_name}')
        raise
    else:
        conn.commit()


def fetch_recent_user_ids(cursor: Cursor) -> list[int]:
    """读取所有启用的用户 account_id 列表"""
    sql = """
        SELECT
            account_id
        FROM T_user_config
        WHERE user_level > 0;
    """
    cursor.execute(sql)
    user_ids = [row[0] for row in cursor.fetchall()]
    if len(user_ids) == 1:
        return user_ids

    # 打乱读取的用户 ID 列表，确保所有用户更新频次
    random.shuffle(user_ids)
    return user_ids


def fetch_user_record(
    cursor: Cursor, account_id: int
) -> tuple[UserRecord | None, UserStats | None]:
    """读取单个用户的配置与战绩快照"""
    # user_stats -> 由其他服务维护的用户最新统计数据，用于判断需要更新的模式
    # user_record -> 用户配置数据，用于记录用户等级、上次查询时间等数据
    sql = """
        SELECT
            c.user_level,
            c.storage_limit,
            UNIX_TIMESTAMP(c.last_query_at),
            s.is_enabled,
            s.is_public,
            s.total_battles,
            s.pve_battles,
            s.pvp_battles,
            s.ranked_battles,
            s.rating_battles,
            s.karma,
            UNIX_TIMESTAMP(s.last_battle_at),
            UNIX_TIMESTAMP(s.next_refresh_at),
            UNIX_TIMESTAMP(s.updated_at)
        FROM T_user_config c
        LEFT JOIN T_user_stats s
          ON c.account_id = s.account_id
        WHERE c.account_id = %s;
    """
    cursor.execute(sql, [account_id])
    row = cursor.fetchone()

    if row is None:
        return None, None

    record = UserRecord(
        user_level=row[0] or 0,
        storage_limit=row[1] or 0,
        last_query_at=int(row[2]) if row[2] is not None else None,
        next_refresh_at=int(row[12]) if row[12] is not None else None
    )

    if row[10] is not None:
        stats = UserStats(
            is_enabled=bool(row[3]),
            is_public=bool(row[4]),
            total_battles=row[5] or 0,
            pve_battles=row[6] or 0,
            pvp_battles=row[7] or 0,
            ranked_battles=row[8] or 0,
            rating_battles=row[9] or 0,
            karma=row[10] or 0,
            last_battle_at=int(row[11]) if row[11] is not None else None,
            updated_at=int(row[13]) if row[13] is not None else None,
        )
    else:
        stats = None

    return record, stats


def deactivate_user(cursor: Cursor, account_id: int) -> None:
    """批量停用用户"""
    sql = """
        UPDATE T_user_config
        SET
            user_level = 0,
            storage_limit = 0
        WHERE account_id = %s;
    """
    cursor.execute(sql, [account_id])
