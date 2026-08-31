import sqlite3
import traceback
from pathlib import Path
from typing import Optional

from logger import logger
from exception import write_exception
from settings import SQLITE_DIR, CREATE_SQL


def season_file(season_id: int) -> Path:
    """返回指定赛季的 SQLite 数据库文件路径"""
    return SQLITE_DIR / f'season_{season_id}.db'

def ensure_clan_battle_table(season_id: int) -> Optional[bool]:
    """确保当前赛季的公会战数据表已创建（SQLite 数据库文件）

    Args:
        season_id: 赛季 ID

    Returns:
        是否成功创建，异常则返回 None
    """
    db_path = season_file(season_id)

    # 文件已存在则无需重复创建
    if db_path.exists():
        return False

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.executescript(CREATE_SQL)
    except Exception as e:
        conn.rollback()
        error_name = type(e).__name__
        logger.error(f'{season_id} | Database operation error: {error_name}')
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc(),
        )
        if db_path.exists():
            db_path.unlink(missing_ok=True)
            logger.warning(f"Corrupted database file deleted: {db_path}")
        return None
    else:
        conn.commit()
        return True
    finally:
        conn.close()

def insert_clan_battles(season_id: int, insert_data_list: list) -> None:
    """批量插入对战明细到赛季 SQLite 数据库

    Args:
        season_id: 赛季 ID
        insert_data_list: 对战明细插入数据列表，为空时跳过插入
    """
    if not insert_data_list:
        return

    db_path = season_file(season_id)
    if not db_path.exists():
        logger.error(f'{season_id} | Database file missing: {db_path}')
        return

    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        insert_sql = """
            INSERT INTO clan_battle (
                battle_time, clan_id, team_number, battle_result,
                battle_rating, stage_type, league, division,
                division_rating, public_rating
            ) VALUES (?,?,?,?,?,?,?,?,?,?);
        """
        cursor.executemany(insert_sql, insert_data_list)
        conn.commit()
    except Exception as e:
        conn.rollback()
        error_name = type(e).__name__
        logger.error(f'{season_id} | Database operation error: {error_name}')
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc(),
        )
    finally:
        conn.close()
