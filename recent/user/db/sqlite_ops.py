import shutil
import sqlite3
import traceback
from contextlib import contextmanager

from loggers import write_exception, logger
from utils import TimeUtils
from settings import DATA_DIR, SQLITE_DIR, CREATE_SQL


def sqlite_file(account_id: int):
    return SQLITE_DIR / f'{account_id}.db'

def remove_file(account_id: int) -> None:
    """删除 SQLite 数据库文件"""
    db_path = sqlite_file(account_id)
    if db_path.exists():
        timestamp = TimeUtils.get_current_timestamp()
        backup_path = DATA_DIR / 'trash' / f'{account_id}_{timestamp}.db'
        shutil.copy2(db_path, backup_path)
        db_path.unlink()

def ensure_database(account_id: int) -> bool:
    """确保数据库文件存在并已初始化"""
    db_path = sqlite_file(account_id)
    if db_path.exists():
        return True
    
    conn = sqlite3.connect(sqlite_file(account_id))
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
def sqlite_read_only(account_id: int):
    """SQLite 上下文管理器（仅读取）"""
    conn = sqlite3.connect(sqlite_file(account_id))
    try:
        cursor = conn.cursor()
        yield cursor
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f'{account_id} | Database operation error: {error_name}')
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc(),
        )
    finally:
        conn.close()

@contextmanager
def sqlite_transaction(account_id: int):
    """SQLite 事务上下文管理器"""
    db_path = sqlite_file(account_id)
    if not db_path.exists():
        logger.error(f'{account_id} | Database file missing')
        raise RuntimeError(f'File `{db_path}` missing')
    
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        yield cursor
    except Exception as e:
        cursor.execute("ROLLBACK")
        error_name = type(e).__name__
        logger.error(f'{account_id} | Database operation error: {error_name}')
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc(),
        )
        raise
    else:
        cursor.execute("COMMIT")
    finally:
        conn.close()