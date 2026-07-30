from sqlite3 import Cursor

from models import UpdateParams, ShipCache

SPECIAL_SHIP_ID_FOR_INDEX = 1_000_000_000

class ShipCacheRepository:
    """ship_latest_cache 表的数据访问对象"""

    @staticmethod
    def load_all(cursor: Cursor) -> ShipCache:
        """读取全部船只缓存数据"""
        sql = """
            SELECT
                ship_id,
                battles,
                snapshot_date
            FROM ship_latest_cache;
        """
        cursor.execute(sql)
        rows = cursor.fetchall()
        if rows is None:
            return None
        return ShipCache.from_rows(rows)

    @staticmethod
    def refresh(cursor: Cursor, battles: int , table: int, params: UpdateParams) -> None:
        """批量刷新 ship_latest_cache（insert / update / delete）"""
        sql = """
            UPDATE ship_latest_cache
            SET
                battles = ?,
                snapshot_date = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE ship_id = ?;
        """
        cursor.execute(sql, [battles, table, SPECIAL_SHIP_ID_FOR_INDEX])

        if params.get('insert'):
            sql = """
                INSERT INTO ship_latest_cache (
                    ship_id, battles, snapshot_date
                ) VALUES (?, ?, ?);
            """
            cursor.executemany(
                sql, params['insert']
            )

        if params.get('update'):
            sql = """
                UPDATE ship_latest_cache
                SET
                    battles = ?,
                    snapshot_date = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ship_id = ?;
            """
            cursor.executemany(
                sql, params['update']
            )

        if params.get('delete'):
            sql = "DELETE FROM ship_latest_cache WHERE ship_id = ?;"
            cursor.executemany(
                sql, params['delete']
            )
