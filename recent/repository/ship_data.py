from sqlite3 import Cursor

from params import ShipDataUpdateParams
from models import (
    DataType,
    BattleMode,
    ShipDataEntry,
    ShipBattleStats
)
from utils import StringUtils


class ShipDataRepository:
    """ship_index_data 表的数据访问对象"""

    @staticmethod
    def read(
        cursor: Cursor, ship_id: int, mode: BattleMode, ship_index: int
    ) -> ShipDataEntry | None:
        """读取单条船只快照数据"""
        sql = """
            SELECT
                data_type_1,
                data_type_2,
                data_type_3
            FROM ship_index_data
            WHERE ship_mode = ?
              AND ship_id = ?
              AND ship_index = ?;
        """
        cursor.execute(sql, [mode.value, ship_id, ship_index])
        result = cursor.fetchone()
        if not result:
            return None

        data = ShipDataEntry()
        if result[0]:
            data.set_type_stats(
                DataType.SOLO,
                ShipBattleStats.from_row(StringUtils.stats_decode(result[0]))
            )
        if result[1]:
            data.set_type_stats(
                DataType.DIV2,
                ShipBattleStats.from_row(StringUtils.stats_decode(result[1]))
            )
        if result[2]:
            data.set_type_stats(
                DataType.DIV3,
                ShipBattleStats.from_row(StringUtils.stats_decode(result[2]))
            )
        return data

    @staticmethod
    def refresh(
        cursor: Cursor, params: ShipDataUpdateParams
    ) -> None:
        """刷新船只明细快照"""
        if params.has_insert_params:
            sql = """
                INSERT INTO ship_index_data (
                    ship_id,
                    ship_mode,
                    ship_index,
                    data_type_1,
                    data_type_2,
                    data_type_3
                ) VALUES (?,?,?,?,?,?);
            """
            cursor.executemany(sql, params.get_insert_params)

        if params.has_update_params:
            sql = """
                UPDATE ship_index_data
                SET
                    data_type_1 = ?,
                    data_type_2 = ?,
                    data_type_3 = ?
                WHERE ship_id = ?
                  AND ship_mode = ?
                  AND ship_index = ?;
            """
            cursor.executemany(sql, params.get_update_params)
