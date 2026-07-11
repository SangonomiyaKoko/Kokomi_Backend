from sqlite3 import Cursor


from app.core import EnvConfig
from app.utils import TimeUtils


TABLE_NAME_LIST = ['ship_daily_snapshot', 'ship_latest_cache', 'daily_snapshot_index', 'user_daily_summary', 'user_recent_stats']

class RecentSummary:
    def read_start_date(cursor: Cursor):
        sql = """
            SELECT 
                MIN(snapshot_date) 
            FROM user_daily_summary;
        """
        cursor.execute(sql)
        return cursor.fetchone()[0]
    
    def read_total_rows(cursor: Cursor):
        total = 0
        for table in TABLE_NAME_LIST:
            cursor.execute(f"SELECT COUNT(*) FROM {table};")
            row_count = cursor.fetchone()[0]
            total += row_count
        return total
    
    def read_daily_summary(cursor: Cursor, current_timestamp: int, start_date: int):
        """"""
        date_list = TimeUtils.get_reset_date_list(current_timestamp, start_date)
        summary = {r_date: None for r_date in date_list}

        sql = """
            SELECT 
                snapshot_date, 
                is_public, 
                total_battles
            FROM user_daily_summary;
        """
        cursor.execute(sql)
        for row in cursor.fetchall():
            if not row[1]:
                summary[row[0]] = -1
            else:
                summary[row[0]] = row[2]

        return summary