from sqlite3 import Cursor

from models import UpdateParams, ShipCache, SPECIAL_SHIP_ID_FOR_INDEX


class ShipCacheRepository:
    """ship_latest_index 表的数据访问对象"""

    @staticmethod
    def load_all(cursor: Cursor) -> ShipCache:
        """读取全部船只缓存数据（含特殊行）"""
        sql = """
            SELECT
                ship_id,
                pvp_battles,
                rank_battles,
                clan_battles,
                pvp_index,
                rank_index,
                clan_index
            FROM ship_latest_index;
        """
        cursor.execute(sql)
        return ShipCache.from_rows(cursor.fetchall())

    @staticmethod
    def record_latest_index(cursor: Cursor, pvp: tuple, rank: tuple, clan: tuple) -> None:
        """写入特殊行：每个模式传 (battles, index)，用于记录各模式最新战斗数与 map 索引（兜底来源）"""
        sql = """
            UPDATE ship_latest_index
            SET
                pvp_battles = ?,
                rank_battles = ?,
                clan_battles = ?,
                pvp_index = ?,
                rank_index = ?,
                clan_index = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE ship_id = ?;
        """
        cursor.execute(sql, [
            pvp[0], rank[0], clan[0],   # 各模式最新战斗场次
            pvp[1], rank[1], clan[1],   # 各模式最新 map 索引
            SPECIAL_SHIP_ID_FOR_INDEX
        ])

    @staticmethod
    def refresh(cursor: Cursor, params: UpdateParams) -> None:
        """批量刷新普通船只行（insert / update / delete），特殊行由 record_latest_index 单独写入"""
        if params.get('insert'):
            sql = """
                INSERT INTO ship_latest_index (
                    ship_id,
                    pvp_battles,
                    rank_battles,
                    clan_battles,
                    pvp_index,
                    rank_index,
                    clan_index
                ) VALUES (?,?,?,?,?,?,?);
            """
            cursor.executemany(
                sql, [p.as_insert_params() for p in params['insert']]
            )

        if params.get('update'):
            sql = """
                UPDATE ship_latest_index
                SET
                    pvp_battles = ?,
                    rank_battles = ?,
                    clan_battles = ?,
                    pvp_index = ?,
                    rank_index = ?,
                    clan_index = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE ship_id = ?;
            """
            cursor.executemany(
                sql, [p.as_update_params() for p in params['update']]
            )

        if params.get('delete'):
            sql = "DELETE FROM ship_latest_index WHERE ship_id = ?;"
            cursor.executemany(
                sql, [p.as_delete_params() for p in params['delete']]
            )
