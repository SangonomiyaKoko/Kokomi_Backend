from sqlite3 import Cursor

from ..models import BattleRecord


class ClanBattleRepository:

    @staticmethod
    def insert_battles(
        cursor: Cursor, record: BattleRecord
    ) -> None:
        """批量插入对战明细"""
        sql = """
            INSERT INTO clan_battle (
                battle_time,
                clan_id,
                team_number,
                victory,
                result,
                rating,
                league,
                division,
                division_rating,
                stage_type,
                stage_progress
            )
            VALUES (
                ?,?,?,?,?,?,?,?,?,?,?
            );
        """
        cursor.execute(sql, record.to_list())

    @staticmethod
    def update_meta(
        cursor: Cursor, record: int, discard: int
    ) -> None:
        """更新数据库统计表"""
        sql = """
            UPDATE database_meta 
            SET 
                metric_value = metric_value + ?
            WHERE metric_key = ?;
        """
        cursor.executemany(sql, [
            [record,'record'],
            [discard, 'discard'],
            [record+discard, 'total']
        ])
