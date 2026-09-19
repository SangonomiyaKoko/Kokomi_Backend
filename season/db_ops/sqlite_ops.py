import sqlite3
import traceback
from pathlib import Path
from contextlib import contextmanager
from typing import Iterator

from sqlite3 import Cursor

from ..logger import logger, write_exception
from ..settings import DATA_DIR, CREATE_SQL


def _file_path(season_id: int) -> Path:
    """返回指定赛季的 SQLite 数据库文件路径"""
    return DATA_DIR / 'local' / f'season_{season_id}.db'


@contextmanager
def sqlite_transaction(season_id: int) -> Iterator[Cursor]:
    """SQLite 自动事务上下文管理器"""
    path = _file_path(season_id)
    if not path.exists():
        logger.error(f'{season_id} | Database file missing')
        raise RuntimeError(f'File missing: {path}')

    conn = sqlite3.connect(path)
    try:
        cursor = conn.cursor()
        cursor.execute("BEGIN IMMEDIATE")
        try:
            yield cursor
        except Exception as e:
            # 操作失败则回滚，回滚失败时保留原始异常
            try:
                cursor.execute("ROLLBACK")
            except Exception:
                pass
            logger.error(
                f'{season_id} | Database operation error: {type(e).__name__}'
            )
            raise
        else:
            # 操作成功则提交
            cursor.execute("COMMIT")
    finally:
        conn.close()


def ensure_database(season_id: int) -> bool:
    """确保指定赛季的数据库文件存在并已初始化"""
    path = _file_path(season_id)
    if path.exists():
        return True

    failed = False
    conn = sqlite3.connect(path)
    try:
        cursor = conn.cursor()
        cursor.executescript(CREATE_SQL)
        conn.commit()
    except Exception as e:
        failed = True
        error_name = type(e).__name__
        error_id = write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
        logger.error(f"{season_id} | ERROR - {error_name} - {error_id}")
        return False
    finally:
        # 需先关闭连接再删除文件，否则 Windows 下会因文件被占用而失败
        conn.close()
        if failed:
            # 清理建表失败留下的残缺文件，避免后续误判为已初始化
            path.unlink(missing_ok=True)

    return True