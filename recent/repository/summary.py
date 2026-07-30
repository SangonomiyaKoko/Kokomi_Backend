from sqlite3 import Cursor

from models import DailySummary, UserStats


class DailySummaryRepository:
    """user_daily_summary 表的数据访问对象"""

    @classmethod
    def hidden(cls, updated_at: int) -> DailySummary:
        """构造一条隐藏战绩记录"""
        return DailySummary(
            is_public=False,
            total_battles=0,
            pve_battles=0,
            pvp_battles=0,
            ranked_battles=0,
            karma=0,
            index_table=None,
            updated_at=updated_at
        )

    @classmethod
    def from_stats(cls, stats: UserStats, index_table: str | None) -> DailySummary:
        """从 UserStats 构造一条记录"""
        return DailySummary(
            is_public=stats.is_public,
            total_battles=stats.total_battles,
            pve_battles=stats.pve_battles,
            pvp_battles=stats.pvp_battles,
            ranked_battles=stats.ranked_battles,
            karma=stats.karma,
            index_table=index_table,
            updated_at=stats.updated_at
        )

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