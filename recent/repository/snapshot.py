from sqlite3 import Cursor

from utils import StringUtils
from models import SingleShipData, ShipBattleStats, UpdateParams


class ShipSnapshotRepository:
    """ship_daily_snapshot 表的数据访问对象"""

    @staticmethod
    def read(cursor: Cursor, ship_id: int, snapshot_date: int) -> SingleShipData | None:
        """读取单条船只快照数据"""
        sql = """
            SELECT snapshot_data
            FROM ship_daily_snapshot
            WHERE ship_id = ?
              AND snapshot_date = ?;
        """
        cursor.execute(sql, [ship_id, snapshot_date])
        result = cursor.fetchone()
        if not result:
            return None
        rows = StringUtils.ship_snapshot_decode(result[0])

        ship_data = SingleShipData(ship_id)
        for index, row in enumerate(rows):
            if not row:
                continue
            ship_data.set_mode_stats(index, ShipBattleStats.from_row(row))
        return ship_data

    @staticmethod
    def refresh(cursor: Cursor, params: UpdateParams) -> None:
        """批量刷新 ship_daily_snapshot（insert / update）"""
        if params.get('insert'):
            sql = """
                INSERT INTO ship_daily_snapshot (
                    ship_id, snapshot_date, snapshot_data
                ) VALUES (?, ?, ?);
            """
            cursor.executemany(
                sql, params['insert']
            )

        if params.get('update'):
            sql = """
                UPDATE ship_daily_snapshot
                SET snapshot_data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE ship_id = ? AND snapshot_date = ?;
            """
            cursor.executemany(
                sql, params['update']
            )