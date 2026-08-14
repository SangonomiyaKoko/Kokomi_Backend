from sqlite3 import Cursor


class RecentStatsRepository:
    """user_recent_stats 表的数据访问对象"""

    @staticmethod
    def insert(cursor: Cursor, params: list) -> None:
        """批量插入 user_recent_stats 记录"""
        if not params:
            return

        sql = """
            INSERT INTO user_recent_stats (
                ship_id,
                data_mode,
                data_type,
                battles,
                wins,
                losses,
                exp,
                damage,
                planes,
                frags,
                survived,
                scout_damage,
                art_agro,
                hit_rate,
                battle_time
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """
        cursor.executemany(sql, params)
