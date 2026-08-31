from sqlite3 import Cursor

from params import ShipLatestUpdateParams, ShipLatestLocalCollection
from models import (
    BattleMode,
    FULL_UPDATE_MODES
)


class ShipLatestRepository:
    """ship_latest_index 表的数据访问对象"""

    @staticmethod
    def load_all(cursor: Cursor) -> dict[BattleMode, ShipLatestLocalCollection]:
        """读取全部船只缓存行"""
        sql = """
            SELECT
                ship_mode,
                ship_id,
                battles,
                data_index
            FROM ship_latest_index;
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        result = {mode: ShipLatestLocalCollection() for mode in FULL_UPDATE_MODES}
        for row in rows:
            ship_mode, ship_id, battles, data_index = row
            result[BattleMode(ship_mode)].set_ship_data(ship_id, battles, data_index)
        return result

    @staticmethod
    def refresh(
        cursor: Cursor, params: ShipLatestUpdateParams
    ) -> None:
        """刷新船只概览缓存"""
        if params.has_insert_params:
            sql = """
                INSERT INTO ship_latest_index (
                    ship_id,
                    ship_mode,
                    battles,
                    win_rate,
                    avg_damage,
                    avg_frags,
                    avg_exp,
                    data_index
                )
                VALUES (?,?,?,?,?,?,?,?);
            """
            cursor.executemany(sql, params.get_insert_params)
        if params.has_update_params:
            sql = """
                UPDATE ship_latest_index
                SET
                    battles = ?,
                    win_rate = ?,
                    avg_damage = ?,
                    avg_frags = ?,
                    avg_exp = ?,
                    data_index = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ship_id = ?
                  AND ship_mode = ?;
            """
            cursor.executemany(sql, params.get_update_params)
