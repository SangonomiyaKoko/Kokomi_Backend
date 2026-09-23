from pymysql.cursors import Cursor

from shard import TimeUtils

from .logger import logger


def get_max_id(cursor: Cursor) -> int:
    """
    获取 T_user_cache 表中最大的 id 值
    
    Args:
        cursor: 数据库游标对象
        
    Returns:
        最大 id 值，若表为空则返回 0
    """
    sql = """
        SELECT 
            MAX(id) 
        FROM T_user_cache;
    """
    cursor.execute(sql)
    row = cursor.fetchone()
    return row[0] if row else 0

def get_version(cursor: Cursor) -> str | None:
    sql = """
        SELECT 
            short_name 
        FROM T_game_version 
        WHERE is_latest = TRUE 
        LIMIT 1;
    """
    cursor.execute(sql)
    data = cursor.fetchone()
    if data:
        return data[0]
    else:
        return None

def read_ship_ids(cursor: Cursor) -> list[int]:
    """读取所有已记录的船只 ID 列表

    Args:
        cursor: 数据库游标

    Returns:
        ship_id 列表
    """
    sql = """
        SELECT 
            ship_id 
        FROM T_ship_base;
    """
    cursor.execute(sql)
    return [row[0] for row in cursor.fetchall()]

def read_ship_data(cursor: Cursor) -> dict:
    """加载船只排行榜基准数据

    从视图读取每艘船的最低场次要求和服务器场均指标，
    用于计算玩家 Rating 的基准值

    Args:
        cursor: 数据库游标

    Returns:
        字典，键为 ship_id，值为 [min_battles, [win_rate, avg_damage, avg_frags]]
    """
    ship_info = {}
    sql = """
        SELECT 
            ship_id, 
            battles, 
            win_rate, 
            avg_damage, 
            avg_frags
        FROM T_ship_stats_by_battles;
    """
    cursor.execute(sql)
    rows = cursor.fetchall()
    for row in rows:
        if row[1] >= 1000:
            ship_info[row[0]] = [row[2], row[3], row[4]]
    return ship_info

def refresh_version(cursor: Cursor, local: str | None, latest: dict):
    # 版本未变，更新 full_name 和 updated_at
    if local and local == latest['short']:
        # 确保永远只有一个version是latest
        sql = """
            UPDATE T_game_version 
            SET 
                is_latest = FALSE 
            WHERE is_latest = TRUE;
        """
        cursor.execute(sql)
        sql = """
            UPDATE T_game_version 
            SET 
                is_latest = TRUE,
                full_name = %s, 
                updated_at = NOW() 
            WHERE short_name = %s;
        """
        cursor.execute(sql, [latest['full'], latest['short']])
        logger.info(f"Game Version: {latest['short']} -> Latest")
        return
    
    # 检查最新version是否存在于table中
    sql = """
        SELECT 
            id 
        FROM T_game_version 
        WHERE short_name = %s;
    """
    cursor.execute(sql,[latest['short']])
    existing = cursor.fetchone()
    if not existing:
        # 插入该版本的数据
        sql = """
            INSERT INTO T_game_version (
                is_latest, short_name, full_name
            ) VALUES (
                FALSE, %s, %s
            );
        """
        cursor.execute(sql, [latest['short'], latest['full']])
    
    # 确保永远只有一个version是latest
    sql = """
        UPDATE T_game_version 
        SET 
            is_latest = FALSE 
        WHERE is_latest = TRUE;
    """
    cursor.execute(sql)
    # 将该记录更新为最新
    sql = """
        UPDATE T_game_version 
        SET 
            is_latest = TRUE, 
            full_name = %s, 
            updated_at = NOW() 
        WHERE short_name = %s;
    """
    cursor.execute(sql, [latest['full'], latest['short']])

    logger.info(
        f"Game Version: "
        f"{local if local else 'NULL'} -> {latest['short']}"
    )

def refersh_tracking_time(cursor: Cursor, tracking_key: str, tracking_type: str):
    sql = f"""
        UPDATE T_tracking_meta 
        SET 
            tracking_value = NOW() 
        WHERE tracking_key = %s 
            AND tracking_type = %s;
    """
    cursor.execute(sql, [tracking_key, tracking_type])

def archive_base_table(cursor: Cursor) -> None:
    """归档 user、clan、ship 基础表的行数到 ARCH 表

    Args:
        cursor: 数据库游标
    """
    base_count_list = [0,0,0,0]
    id_col_dict = {
        'user': 'account_id',
        'clan': 'clan_id',
        'ship': 'ship_id'
    }
    # 查询当前数据行数
    i = 1
    for index in ['user', 'clan', 'ship']:
        id_col = id_col_dict.get(index)

        sql = f"SELECT COUNT(*) FROM T_{index}_base;"
        cursor.execute(sql)
        base_count = cursor.fetchone()[0]

        sql_range = f"""
            SELECT 
                COALESCE(MIN({id_col}), 0), 
                COALESCE(MAX({id_col}), 0) 
            FROM T_{index}_base;
        """
        cursor.execute(sql_range)
        min_id, max_id = cursor.fetchone()

        sql = """
            UPDATE T_base_id
            SET
                counts = %s,
                min_id = %s,
                max_id = %s
            WHERE meta = %s;
        """
        cursor.execute(sql, [base_count, min_id, max_id, index])

        base_count_list[0] += base_count
        base_count_list[i] += base_count

        i += 1

    logger.info(
        'Base table archived - User: %s | Clan: %s | Ship: %s',
        base_count_list[1], base_count_list[2], base_count_list[3]
    )
