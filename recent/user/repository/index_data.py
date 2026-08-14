from sqlite3 import Cursor

from models import (
    ShipData,
    ShipBattleStats,
    UpdateParams,
    BattleMode,
    DataType,
)
from utils import StringUtils


class ShipIndexDataRepository:
    """ship_index_data 表的数据访问对象"""

    @staticmethod
    def read(
        cursor: Cursor, ship_id: int, mode: BattleMode, ship_index: int
    ) -> ShipData | None:
        """读取单条船只快照数据"""
        sql = """
            SELECT data_type_1, data_type_2, data_type_3
            FROM ship_index_data
            WHERE ship_mode = ?
              AND ship_id = ?
              AND ship_index = ?;
        """
        cursor.execute(sql, [mode.value, ship_id, ship_index])
        result = cursor.fetchone()
        if not result:
            return None

        data = ShipData()
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
    def refresh(cursor: Cursor, params: UpdateParams) -> None:
        """批量刷新 ship_index_data（insert / update）"""
        if not params:
            return

        if params.get('insert'):
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
            cursor.executemany(
                sql, [p.as_insert_params() for p in params['insert']]
            )

        if params.get('update'):
            sql = """
                UPDATE ship_index_data
                SET
                    data_type_1 = ?,
                    data_type_2 = ?,
                    data_type_3 = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ship_id = ?
                  AND ship_mode = ?
                  AND ship_index = ?;
            """
            cursor.executemany(
                sql, [p.as_update_params() for p in params['update']]
            )
