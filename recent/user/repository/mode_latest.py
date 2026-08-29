from sqlite3 import Cursor

from models import BattleMode
from params import (
    ModeLatestUpdateParams,
    ModeLatestLocalEntry
)


class ModeLatestRepository:
    """mode_latest_index 表的数据访问对象"""

    @staticmethod
    def load_all(cursor: Cursor) -> dict[BattleMode, ModeLatestLocalEntry]:
        """读取各模式最新状态"""
        sql = """
            SELECT
                ship_mode,
                battles,
                mode_index,
                update_time
            FROM mode_latest_index;
        """
        cursor.execute(sql)
        return {
            BattleMode(row[0]): ModeLatestLocalEntry(
                battles=row[1],
                mode_index=row[2],
                update_time=row[3]
            )
            for row in cursor.fetchall()
        }

    @staticmethod
    def refresh(
        cursor: Cursor, params: ModeLatestUpdateParams,
    ) -> None:
        """刷新模式概览数据"""
        if params.has_special_params:
            sql = """
                UPDATE mode_latest_index
                SET
                    update_time = ?
                WHERE ship_mode = ?;
            """
            cursor.executemany(sql, [params.clan_special_update_params, BattleMode.CLAN.value])

        if params.has_update_params:
            sql = """
                UPDATE mode_latest_index
                SET
                    battles = ?,
                    win_rate = ?,
                    avg_damage = ?,
                    avg_frags = ?,
                    avg_exp = ?,
                    mode_index = ?,
                    update_time = ?
                WHERE ship_mode = ?;
            """
            cursor.executemany(sql, params.get_update_params)
