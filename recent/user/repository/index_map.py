from sqlite3 import Cursor

from models import UpdateParams


class ShipIndexMapRepository:
    """ship_index_map 表的数据访问对象"""

    @staticmethod
    def refresh(cursor: Cursor, params: UpdateParams) -> None:
        """批量刷新 ship_index_map（insert / update）"""
        if not params:
            return

        if params.get('insert'):
            sql = """
                INSERT INTO ship_index_map (
                    ship_mode,
                    ship_index,
                    ships,
                    battles,
                    wins,
                    damage,
                    frags,
                    exp,
                    index_map
                ) VALUES (?,?,?,?,?,?,?,?,?);
            """
            cursor.execute(
                sql, params['insert'].as_insert_params()
            )

        if params.get('update'):
            sql = """
                UPDATE ship_index_map
                SET
                    ships = ?,
                    battles = ?,
                    wins = ?,
                    damage = ?,
                    frags = ?,
                    exp = ?,
                    index_map = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ship_mode = ?
                  AND ship_index = ?;
            """
            cursor.execute(
                sql, params['update'].as_update_params()
            )
