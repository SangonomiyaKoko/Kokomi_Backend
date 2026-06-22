from pymysql.cursors import Cursor

def get_recent_users(cursor: Cursor):
    sql = """
        SELECT 
            c.account_id, 
            c.user_level, 
            c.storage_limit, 
            s.is_enabled, 
            s.is_public, 
            s.total_battles, 
            s.pve_battles, 
            s.pvp_battles, 
            s.ranked_battles, 
            s.karma,
            UNIX_TIMESTAMP(s.updated_at)
        FROM T_user_config c
        LEFT JOIN T_user_stats s
          ON c.account_id = s.account_id
        WHERE c.user_level > 0;
    """
    cursor.execute(sql)
    return cursor.fetchall()

def disable_user(cursor: Cursor, account_id: int):
    sql = """
        UPDATE T_user_config 
        SET 
            user_level = 0, 
            storage_limit = 0 
        WHERE account_id = %s;
    """
    cursor.execute(sql, [account_id])