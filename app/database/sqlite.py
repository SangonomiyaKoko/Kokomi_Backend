import shutil
import sqlite3
from pathlib import Path
from sqlite3 import Connection

from app.core import EnvConfig
from app.utils import TimeUtils

class SQLiteConnection:
    def delete_db(account_id: int) -> None:
        """将文件放入回收站，非直接删除"""
        db_path = EnvConfig.SQLITE_DIR / f'{account_id}.db'
        if not db_path.exists():
            return
        
        current_timestamp = TimeUtils.timestamp()
        backup_path = EnvConfig.DATA_DIR / 'trash' / f'{account_id}_{current_timestamp}.db'
        shutil.copy2(db_path, backup_path)
        db_path.unlink()

    def clear_recent_data(account_id: int) -> None:
        """删除数据库文件中 user_recent_stats 表中所有数据"""
        db_path = EnvConfig.SQLITE_DIR / f'{account_id}.db'
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