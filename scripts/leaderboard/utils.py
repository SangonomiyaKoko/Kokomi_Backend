import gzip
import json
import pymysql
from datetime import datetime, timezone

from middlewares import db_pool


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def get_max_id():
    # 先获取数据库中id最大值，确定循环上限
    conn = db_pool.connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        sql = """
            SELECT 
                MAX(id) AS max_id 
            FROM user_cache;
        """
        cursor.execute(sql)
        data = cursor.fetchone()
        return data['max_id']
    finally:
        cursor.close()
        conn.close()

def decompress(gzip_bytes: bytes):
    # 数据解压
    if gzip_bytes:
        decompressed = gzip.decompress(gzip_bytes)
        return json.loads(decompressed)
    else:
        return None