import sqlite3
from sqlite3 import Cursor

from app.core import EnvConfig


class CalculateRecent:
    def _read_daily_summary(cursor: Cursor):
        sql = """
            SELECT 
                snapshot_date, 
                index_table, 
                updated_at
            FROM user_daily_summary 
            ORDER BY snapshot_date;
        """
        cursor.execute(sql)
        result = {}
        for row in cursor.fetchall():
            result[row[0]] = [row[1], row[2]]
        return result
    
    def _read_snapshot_index(cursor: Cursor, snapshot_date: int):
        sql = """
            SELECT 
                ship_map 
            FROM daily_snapshot_index 
            WHERE snapshot_date = ?;
        """
        cursor.execute(sql, [snapshot_date])
        data = cursor.fetchone()
        if data:
            fields = data[0].split(',')
            result = {}
            for f in fields:
                data = f.split(':')
                result[data[0]] = data[1]
            return result
        else:
            return None
    
    def _read_daily_snapshot(cursor: Cursor, ship_id: int, snapshot_date: str):
        sql = """
            SELECT 
                snapshot_data 
            FROM ship_daily_snapshot 
            WHERE ship_id = ? 
              AND snapshot_date = ?;
        """
        cursor.execute(sql, [ship_id, snapshot_date])
        data = cursor.fetchone()
        if data:
            fields = data[0].split(';')
            result = []
            for f in fields:
                if f == '':
                    result.append(None)
                else:
                    result.append(eval(f))
            return result
        else:
            return None
        
    def _calc_recent(new_snapshot: list, old_snapshot: list):
        result = []
        for idx in range(4):
            new_data = new_snapshot[idx]
            old_data = old_snapshot[idx]

            # 只有两者都存在时才计算差值
            if new_data is None:
                result.append([])
                continue

            if old_data is None:
                old_data = [0 * 12]

            # 计算各字段差值（新 - 旧）
            delta_battles = new_data[0] - old_data[0]
            if delta_battles <= 0:
                result.append([])
                continue

            delta_wins = new_data[1] - old_data[1]
            delta_losses = new_data[2] - old_data[2]
            delta_damage = new_data[3] - old_data[3]
            delta_frags = new_data[4] - old_data[4]
            delta_original_exp = new_data[8] - old_data[8]
            delta_scouting_damage = new_data[6] - old_data[6]
            delta_art_agro = new_data[7] - old_data[7]
            delta_planes_killed = new_data[9] - old_data[9]
            delta_survived = new_data[5] - old_data[5]

            delta_hits = new_data[10] - old_data[10]
            delta_shots = new_data[11] - old_data[11]

            result.append([
                delta_battles, delta_wins, delta_losses, delta_damage,
                delta_frags, delta_original_exp, delta_scouting_damage,
                delta_art_agro, delta_planes_killed, delta_survived, 
                delta_hits, delta_shots
            ])

        return result

    @classmethod
    def calc_recent(cls, account_id: int, start_date: int, end_date: int):
        db_path = EnvConfig.SQLITE_DIR / f'{account_id}.db'

        with sqlite3.connect(db_path) as conn:
            try:
                cursor = conn.cursor()
                recent = {}
                daily_summary = cls._read_daily_summary(cursor)
                if daily_summary[start_date][0] == daily_summary[end_date][0]:
                    return recent
                start_data = cls._read_snapshot_index(cursor, daily_summary[start_date][0])
                end_data = cls._read_snapshot_index(cursor, daily_summary[end_date][0])

                for ship_id, snapshot_date in end_data.items():
                    if ship_id not in start_data:
                        recent[ship_id] = cls._calc_recent(
                            cls._read_daily_snapshot(cursor, ship_id, snapshot_date),
                            [[], [], [], []]
                        )
                    elif snapshot_date != start_data[ship_id]:
                        recent[ship_id] = cls._calc_recent(
                            cls._read_daily_snapshot(cursor, ship_id, snapshot_date),
                            cls._read_daily_snapshot(cursor, ship_id, start_data[ship_id])
                        )

                return recent
            finally:
                cursor.close()