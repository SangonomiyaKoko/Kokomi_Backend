import shutil
import sqlite3
from pathlib import Path
from typing import Iterator
from sqlite3 import Cursor
from contextlib import contextmanager

from app.core import EnvConfig, api_logger
from app.utils import TimeUtils

class SQLiteConnection:
    def _sqlite_file(account_id: int) -> Path:
        """返回用户 SQLite 数据库路径"""
        return EnvConfig.SQLITE_DIR / f'{account_id}.db'

    @classmethod
    def delete_db(cls, account_id: int) -> None:
        """将文件放入回收站，非直接删除"""
        db_path = cls._sqlite_file(account_id)
        if not db_path.exists():
            return
        
        current_timestamp = TimeUtils.timestamp()
        backup_path = EnvConfig.DATA_DIR / 'trash' / f'{account_id}_{current_timestamp}.db'
        shutil.copy2(db_path, backup_path)
        db_path.unlink()

    @classmethod
    def clear_recent_data(cls, account_id: int) -> None:
        """删除数据库文件中 user_recent_stats 表中所有数据"""
        db_path = cls._sqlite_file(account_id)
        if not db_path.exists():
            return

        conn = None
        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("DELETE FROM user_recent_stats;")
            conn.commit()
        except:
            if conn:
                conn.rollback()
            raise
        finally:
            if conn:
                conn.close()

    @classmethod
    @contextmanager
    def read_only_cursor(cls, account_id: int) -> Iterator[Cursor]:
        """SQLite 上下文管理器，仅读取"""
        db_path = cls._sqlite_file(account_id)
        if not db_path.exists():
            raise RuntimeError(f'File `{db_path}` missing')

        conn = sqlite3.connect(db_path)
        try:
            cursor = conn.cursor()
            yield cursor
        finally:
            conn.close()

    @classmethod
    @contextmanager
    def auto_transaction_cursor(cls, account_id: int) -> Iterator[Cursor]:
        """SQLite 自动事务上下文管理器"""
        db_path = cls._sqlite_file(account_id)
        if not db_path.exists():
            raise RuntimeError(f'File `{db_path}` missing')

        conn = sqlite3.connect(db_path)
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            yield cursor
        except Exception:
            # 操作失败则回滚，回滚失败时保留原始异常
            try:
                cursor.execute("ROLLBACK")
            except Exception as e:
                api_logger.error(f"Rolled back failed: {type(e).__name__}")
            else:
                api_logger.warning("Auto transaction rolled back due to exception")
            raise
        else:
            # 操作成功则提交
            cursor.execute("COMMIT")
        finally:
            conn.close()