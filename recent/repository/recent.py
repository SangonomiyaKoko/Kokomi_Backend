from sqlite3 import Cursor

from models import UpdateParams


class RecentStatsRepository:
    """user_recent_stats 表的数据访问对象"""

    @staticmethod
    def insert(cursor: Cursor, params: list) -> None:
        """批量插入 user_recent_stats 记录"""
        if not params:
            return
        
        sql = """
            INSERT INTO user_recent_stats (
                ship_id, mode, battles, wins, losses, damage, frags,
                original_exp, scouting_damage, art_agro, planes_killed,
                survived, hit_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        cursor.executemany(
            sql, params
        )