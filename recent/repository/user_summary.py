from sqlite3 import Cursor

from params import UserSummaryLocalEntry, UserSummaryUpdateParams


class UserSummaryRepository:
    """user_daily_summary 表的数据访问对象"""
    @staticmethod
    def load_all(cursor: Cursor) -> dict[int, UserSummaryLocalEntry]:
        """读取 user_daily_summary 全部记录"""
        sql = """
            SELECT
                snapshot_date,
                is_public,
                total_battles,
                pve_battles,
                pvp_battles,
                rank_battles,
                clan_battles,
                karma,
                pvp_index,
                rank_index,
                clan_index,
                update_time
            FROM user_daily_summary
            ORDER BY snapshot_date;
        """
        cursor.execute(sql)
        result = {}
        for row in cursor.fetchall():
            result[int(row[0])] = UserSummaryLocalEntry.from_row(row[1:])
        return result

    @staticmethod
    def insert(
        cursor: Cursor, snapshot_date: int, summary: UserSummaryLocalEntry
    ) -> None:
        """插入一条用户每日摘要"""
        sql = """
            INSERT INTO user_daily_summary (
                snapshot_date,
                is_public,
                total_battles,
                pve_battles,
                pvp_battles,
                rank_battles,
                clan_battles,
                karma,
                pvp_index,
                rank_index,
                clan_index,
                update_time
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?);
        """
        cursor.execute(sql, [snapshot_date] + summary.to_list())

    @staticmethod
    def refresh(
        cursor: Cursor, params: UserSummaryUpdateParams
    ) -> None:
        """刷新用户每日摘要"""
        if params.has_insert_params:
            sql = """
                INSERT INTO user_daily_summary (
                    snapshot_date,
                    is_public,
                    total_battles,
                    pve_battles,
                    pvp_battles,
                    rank_battles,
                    clan_battles,
                    karma,
                    pvp_index,
                    rank_index,
                    clan_index,
                    update_time
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?);
            """
            cursor.executemany(sql, params.get_insert_params)

        if params.has_update_params:
            sql = """
                UPDATE user_daily_summary
                SET
                    is_public = ?,
                    total_battles = ?,
                    pve_battles = ?,
                    pvp_battles = ?,
                    rank_battles = ?,
                    clan_battles = ?,
                    karma = ?,
                    pvp_index = ?,
                    rank_index = ?,
                    clan_index = ?,
                    update_time = ?
                WHERE snapshot_date = ?;
            """
            cursor.executemany(sql, params.get_update_params)
