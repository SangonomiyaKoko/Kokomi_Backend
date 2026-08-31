import shutil
import sqlite3
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from loggers import logger, write_exception
from utils import TimeUtils
from settings import (
    DATA_DIR, 
    SQLITE_DIR, 
    CREATE_SQL
)


def _sqlite_file(account_id: int) -> Path:
    """返回用户 SQLite 数据库路径"""
    return SQLITE_DIR / f'{account_id}.db'


def remove_file(account_id: int) -> None:
    """删除 SQLite 数据库文件"""
    db_path = _sqlite_file(account_id)
    if db_path.exists():
        # 考虑到回档需要，删除操作实际是将文件转移到待删除文件夹
        # 为了防止文件同名，因此用操作时间戳当文件名后续做为区分
        timestamp = TimeUtils.get_current_timestamp()
        backup_path = DATA_DIR / 'trash' / f'{account_id}_{timestamp}.db'
        shutil.copy2(db_path, backup_path)
        db_path.unlink()


def ensure_database(account_id: int) -> bool:
    """确保数据库文件存在并已初始化"""
    db_path = _sqlite_file(account_id)
    if db_path.exists():
        return True

    conn = sqlite3.connect(_sqlite_file(account_id))
    try:
        cursor = conn.cursor()
        cursor.executescript(CREATE_SQL)
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f'{account_id} | Database operation error: {error_name}')
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc(),
        )
        if conn:
            conn.close()
        if db_path.exists():
            db_path.unlink(missing_ok=True)
            logger.warning(f"Corrupted database file deleted: {db_path}")
        return False
    else:
        conn.commit()
        conn.close()
        return True


@contextmanager
def sqlite_read_only(account_id: int) -> Iterator[sqlite3.Cursor]:
    """SQLite 上下文管理器，仅读取"""
    conn = sqlite3.connect(_sqlite_file(account_id))
    try:
        cursor = conn.cursor()
        yield cursor
    except Exception as e:
        logger.error(f'{account_id} | Database operation error: {type(e).__name__}')
        raise
    finally:
        conn.close()


@contextmanager
def sqlite_transaction(account_id: int) -> Iterator[sqlite3.Cursor]:
    """SQLite 自动事务上下文管理器"""
    db_path = _sqlite_file(account_id)
    if not db_path.exists():
        logger.error(f'{account_id} | Database file missing')
        raise RuntimeError(f'File `{db_path}` missing')

    conn = sqlite3.connect(db_path)
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        yield cursor
    except Exception as e:
        # 操作失败则回滚，回滚失败时保留原始异常
        if cursor is not None:
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
        logger.error(f'{account_id} | Database operation error: {type(e).__name__}')
        raise
    else:
        # 操作成功则提交
        cursor.execute("COMMIT")
    finally:
        conn.close()
