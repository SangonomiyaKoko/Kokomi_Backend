import traceback
from pymysql.cursors import Cursor
from contextlib import contextmanager

from models import UserStats, UserRecord
from loggers import write_exception, logger

@contextmanager
def mysql_transaction(conn, account_id: int):
    """MySQL 事务上下文管理器"""
    try:
        with conn.cursor() as cur:
            yield cur
    except Exception as e:
        conn.rollback()
        error_name = type(e).__name__
        logger.error(f'{account_id} | Database operation error: {error_name}')
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc(),
        )
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
    return [row[0] for row in cursor.fetchall()]


def fetch_user_record(cursor: Cursor, account_id: int) -> tuple[UserRecord, UserStats]:
    """读取单个用户的配置与战绩快照"""
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
        next_refresh_at=int(row[11]) if row[11] is not None else None
    )

    if row[10] is not None:
        stats = UserStats(
            is_enabled=bool(row[3]),
            is_public=bool(row[4]),
            total_battles=row[5] or 0,
            pve_battles=row[6] or 0,
            pvp_battles=row[7] or 0,
            ranked_battles=row[8] or 0,
            karma=row[9] or 0,
            last_battle_at=int(row[10]) if row[10] is not None else None,
            updated_at=int(row[12]),
        )
    else:
        stats = None
        
    return record, stats
    


def deactivate_user(cursor: Cursor, account_id: int) -> None:
    """将指定用户的 user_level 与 storage_limit 置为 0"""
    sql = """
        UPDATE T_user_config
        SET
            user_level = 0,
            storage_limit = 0
        WHERE account_id = %s;
    """
    cursor.execute(sql, [account_id])
