from sqlite3 import Cursor

from params import UserRecentUpdateParams

class UserRecentRepository:
    """user_recent_stats 表的数据访问对象"""

    @staticmethod
    def refresh(
        cursor: Cursor, params: UserRecentUpdateParams
    ) -> None:
        """写入用户近期战斗数据"""
        if params.has_insert_params:
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
            cursor.executemany(sql, params.get_insert_params)
