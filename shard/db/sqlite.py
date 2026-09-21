import shutil
import sqlite3
from pathlib import Path
from typing import Iterator
from contextlib import contextmanager

from sqlite3 import Cursor

from ..utils.time import TimeUtils


class SQLiteOPS:
    @staticmethod
    def user_db_path(sqlite_dir: Path, account_id: int) -> Path:
        return sqlite_dir / f'{account_id}.db'

    @staticmethod
    def season_db_path(data_dir: Path, season_id: int) -> Path:
        return data_dir / 'season' / f'{season_id}.db'

    @staticmethod
    def version_db_path(data_dir: Path, version: str) -> Path:
        return data_dir / 'version' / f'{version}.db'

    @staticmethod
    def remove_user_db(sqlite_dir: Path, data_dir: Path, account_id: int) -> None:
        """将 SQLite 数据库文件转移到待删除目录

        考虑到回档需要，删除操作实际是把文件转移而非直接删除；
        为防止文件同名，用操作时间戳作为文件名后缀区分
        """
        fp = sqlite_dir / f'{account_id}.db'
        if not fp.exists():
            return

        ts = TimeUtils.timestamp()
        backup_path = data_dir / 'trash' / f'{fp.stem}_{ts}{fp.suffix}'
        shutil.copy2(fp, backup_path)
        fp.unlink()

    @staticmethod
    def ensure_database(path: Path, create_sql: str) -> bool:
        """确保数据库文件存在，返回存在或是否成功初始化"""
        if path.exists():
            return True

        failed = False
        conn = sqlite3.connect(path)
        try:
            cursor = conn.cursor()
            cursor.executescript(create_sql)
            conn.commit()
        except Exception:
            failed = True
            return False
        finally:
            # 需先关闭连接再删除文件
            # 否则 Windows 下会因文件被占用而失败
            conn.close()
            if failed:
                path.unlink(missing_ok=True)

        return True

    @staticmethod
    @contextmanager
    def read_only(fp: Path) -> Iterator[Cursor]:
        """SQLite 上下文管理器，仅读取"""
        if not fp.exists():
            raise FileNotFoundError(f'File missing: {fp}')
        
        conn = sqlite3.connect(fp)
        try:
            cursor = conn.cursor()
            yield cursor
        finally:
            conn.close()

    @staticmethod
    @contextmanager
    def transaction(fp: Path) -> Iterator[Cursor]:
        """SQLite 自动事务上下文管理器"""
        if not fp.exists():
            raise FileNotFoundError(f'File missing: {fp}')
        
        conn = sqlite3.connect(fp)
        cursor = None
        try:
            cursor = conn.cursor()
            cursor.execute("BEGIN IMMEDIATE")
            yield cursor
        except Exception:
            # 操作失败则回滚
            if cursor is not None:
                try:
                    cursor.execute("ROLLBACK")
                except Exception:
                    pass
            raise
        else:
            # 操作成功则提交
            cursor.execute("COMMIT")
        finally:
            conn.close()
