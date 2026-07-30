from sqlite3 import Cursor

from models import UpdateParams


class SnapshotIndexRepository:
    """daily_snapshot_index 表的数据访问对象"""

    @staticmethod
    def refresh(
        cursor: Cursor, params: UpdateParams
    ) -> None:
        """批量刷新 daily_snapshot_index（insert / update）"""
        if params.get('insert'):
            sql = """
                INSERT INTO daily_snapshot_index (
                    snapshot_date, ship_count, ship_map
                ) VALUES (?, ?, ?);
            """
            cursor.execute(
                sql, params['insert']
            )

        if params.get('update'):
            sql = """
                UPDATE daily_snapshot_index
                SET 
                    ship_count = ?, 
                    ship_map = ?, 
                    updated_at = CURRENT_TIMESTAMP
                WHERE snapshot_date = ?;
            """
            cursor.execute(
                sql, params['update']
            )