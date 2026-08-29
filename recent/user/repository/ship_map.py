from sqlite3 import Cursor

from params import ShipMapUpdateParams


class ShipMapRepository:
    """ship_index_map 表的数据访问对象"""

    @staticmethod
    def refresh(
        cursor: Cursor, params: ShipMapUpdateParams
    ) -> None:
        """刷新模式船只索引映射"""
        if params.has_insert_params:
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
                    index_map,
                    update_time
                ) VALUES (?,?,?,?,?,?,?,?,?,?);
            """
            cursor.executemany(sql, params.get_insert_params)

        if params.has_update_params:
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
                    update_time = ?
                WHERE ship_mode = ?
                  AND ship_index = ?;
            """
            cursor.executemany(sql, params.get_update_params)
