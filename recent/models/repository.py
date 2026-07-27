from sqlite3 import Cursor

from utils import StringUtils

from .plan import CachePlan, SnapshotPlan, DailyIndexPlan, RecentPlan
from .ship_stats import ShipBattleStats, SingleShipData
from .tables import DailySummary


class DailySummaryRepository:
    """user_daily_summary 表的数据访问对象"""

    @staticmethod
    def count(cursor: Cursor) -> int:
        """读取 user_daily_summary 总记录数"""
        sql = """
            SELECT COUNT(*)
            FROM user_daily_summary;
        """
        cursor.execute(sql)
        row = cursor.fetchone()
        return row[0]

    @staticmethod
    def load_one(cursor: Cursor, snapshot_date: int) -> DailySummary | None:
        """读取 user_daily_summary 单条记录"""
        sql = """
            SELECT
                is_public,
                total_battles,
                pve_battles,
                pvp_battles,
                ranked_battles,
                karma,
                index_table,
                updated_at
            FROM user_daily_summary
            WHERE snapshot_date = ?;
        """
        cursor.execute(sql, [snapshot_date])
        row = cursor.fetchone()
        if row:
            return DailySummary.from_row(row)
        return None

    @staticmethod
    def load_all(cursor: Cursor) -> dict[int, DailySummary]:
        """读取 user_daily_summary 全部记录"""
        sql = """
            SELECT
                snapshot_date,
                is_public,
                total_battles,
                pve_battles,
                pvp_battles,
                ranked_battles,
                karma,
                index_table,
                updated_at
            FROM user_daily_summary
            ORDER BY snapshot_date;
        """
        cursor.execute(sql)
        result = {}
        for row in cursor.fetchall():
            result[int(row[0])] = DailySummary.from_row(row[1:])
        return result

    @staticmethod
    def insert(cursor: Cursor, snapshot_date: int, summary: DailySummary) -> None:
        """插入一条 user_daily_summary 记录"""
        sql = """
            INSERT INTO user_daily_summary (
                snapshot_date,
                is_public,
                total_battles,
                pve_battles,
                pvp_battles,
                ranked_battles,
                karma,
                index_table,
                updated_at
            ) VALUES (
                ?,?,?,?,?,?,?,?,?
            );
        """
        cursor.execute(sql, [snapshot_date] + summary.to_row())

    @staticmethod
    def update(cursor: Cursor, snapshot_date: int, summary: DailySummary) -> None:
        """更新指定日期的 user_daily_summary 记录"""
        sql = """
            UPDATE user_daily_summary
            SET
                is_public = ?,
                total_battles = ?,
                pve_battles = ?,
                pvp_battles = ?,
                ranked_battles = ?,
                karma = ?,
                index_table = ?,
                updated_at = ?
            WHERE snapshot_date = ?;
        """
        cursor.execute(sql, summary.to_row() + [snapshot_date])


class ShipCacheRepository:
    """ship_latest_cache 表的数据访问对象"""

    @staticmethod
    def load_all(cursor: Cursor) -> dict[str, tuple[int, int]]:
        """读取全部船只缓存数据"""
        sql = """
            SELECT
                ship_id,
                battles,
                snapshot_date
            FROM ship_latest_cache;
        """
        cursor.execute(sql)
        data = {}
        for row in cursor.fetchall():
            data[str(row[0])] = (row[1], row[2])
        return data

    @staticmethod
    def refresh(cursor: Cursor, params: CachePlan) -> None:
        """批量刷新 ship_latest_cache（insert / update / delete）"""
        if params.get('insert'):
            sql = """
                INSERT INTO ship_latest_cache (
                    ship_id, battles, snapshot_date
                ) VALUES (?, ?, ?);
            """
            cursor.executemany(
                sql, [p.as_insert_params() for p in params['insert']]
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
                sql, [p.as_update_params() for p in params['update']]
            )

        if params.get('delete'):
            sql = "DELETE FROM ship_latest_cache WHERE ship_id = ?;"
            cursor.executemany(
                sql, [p.as_delete_params() for p in params['delete']]
            )


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
        rows = StringUtils.ship_snapshot_decode(result)

        ship_data = SingleShipData(ship_id)
        for index, row in enumerate(rows):
            if not row:
                continue
            ship_data.set_mode_stats(index, ShipBattleStats.from_row(row))
        return ship_data

    @staticmethod
    def refresh(cursor: Cursor, params: SnapshotPlan) -> None:
        """批量刷新 ship_daily_snapshot（insert / update）"""
        if params.get('insert'):
            sql = """
                INSERT INTO ship_daily_snapshot (
                    ship_id, snapshot_date, snapshot_data
                ) VALUES (?, ?, ?);
            """
            cursor.executemany(
                sql, [p.as_insert_params() for p in params['insert']]
            )

        if params.get('update'):
            sql = """
                UPDATE ship_daily_snapshot
                SET snapshot_data = ?, updated_at = CURRENT_TIMESTAMP
                WHERE ship_id = ? AND snapshot_date = ?;
            """
            cursor.executemany(
                sql, [p.as_update_params() for p in params['update']]
            )


class SnapshotIndexRepository:
    """daily_snapshot_index 表的数据访问对象"""

    @staticmethod
    def insert(
        cursor: Cursor, snapshot_date: int, ship_count: int, ship_map: str
    ) -> None:
        """插入一条 daily_snapshot_index 记录"""
        sql = """
            INSERT INTO daily_snapshot_index (
                snapshot_date, ship_count, ship_map
            ) VALUES (?, ?, ?);
        """
        cursor.execute(sql, [snapshot_date, ship_count, ship_map])

    @staticmethod
    def refresh(
        cursor: Cursor, index_plan: DailyIndexPlan
    ) -> None:
        """批量刷新 daily_snapshot_index（insert / update）"""
        if index_plan.get('insert'):
            sql = """
                INSERT INTO daily_snapshot_index (
                    snapshot_date, ship_count, ship_map
                ) VALUES (?, ?, ?);
            """
            cursor.executemany(
                sql, [p.as_insert_params() for p in index_plan['insert']]
            )

        if index_plan.get('update'):
            sql = """
                UPDATE daily_snapshot_index
                SET ship_count = ?, ship_map = ?, updated_at = CURRENT_TIMESTAMP
                WHERE snapshot_date = ?;
            """
            cursor.executemany(
                sql, [p.as_update_params() for p in index_plan['update']]
            )


class RecentStatsRepository:
    """user_recent_stats 表的数据访问对象"""

    @staticmethod
    def insert(cursor: Cursor, params: RecentPlan) -> None:
        """批量插入 user_recent_stats 记录"""
        if not params:
            return
        sql = """
            INSERT INTO user_recent_stats (
                ship_id, mode, battles, wins, losses, damage, frags,
                original_exp, scouting_damage, art_agro, planes_killed,
                survived, hit_rate
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);
        """
        cursor.executemany(
            sql, [p.as_insert_params() for p in params]
        )
