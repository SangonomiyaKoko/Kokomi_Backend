import traceback
from pymysql import Connection
from pymysql.cursors import Cursor
from typing import Optional

from logger import logger
from exception import write_exception
from utils import get_rating_level
from settings import CLAN_INIT_TABLE_LIST


def ensure_clan_battle_table(cursor: Cursor, season_id: int) -> Optional[bool]:
    """确保当前赛季的公会战数据表已创建

    Args:
        conn: 数据库连接
        season_id: 赛季 ID

    Returns:
        是否成功创建，异常则返回None
    """
    table_name = f'S_clan_battle_{season_id}'

    # 检查表是否存在
    sql = "SHOW TABLES LIKE %s;"
    cursor.execute(sql, [table_name])
    existing = cursor.fetchone()
    
    # 不存在则创建
    if not existing:
        sql = f"""
        CREATE TABLE IF NOT EXISTS {table_name} (
            id               INT          AUTO_INCREMENT,
            battle_time      TIMESTAMP    NOT NULL,
            clan_id          BIGINT       NOT NULL,
            team_number      TINYINT      NOT NULL,
            battle_result    BOOLEAN      NOT NULL,
            battle_rating    VARCHAR(5)  DEFAULT NULL,
            battle_stage     VARCHAR(5)  DEFAULT NULL,
            league           TINYINT      DEFAULT NULL,
            division         TINYINT      DEFAULT NULL,
            division_rating  INT          DEFAULT NULL,
            public_rating    INT          DEFAULT NULL,
            stage_type       TINYINT      DEFAULT NULL,
            stage_progress   VARCHAR(5)   DEFAULT NULL,
            created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id),
            INDEX idx_time (battle_time),
            INDEX idx_cid (clan_id)
        );
        """
        cursor.execute(sql)
        return True
    else:
        return False

def need_update(conn: Connection, tracking_key: str, tracking_type: str) -> bool:
    """检查并更新数据追踪状态，判断是否需要执行更新任务

    如果追踪记录不存在或距上次更新超过 86400 秒（24小时），
    则更新追踪时间戳并返回 True，否则返回 False

    Args:
        conn: 数据库连接
        tracking_key: 追踪键，用于标识具体的追踪对象
        tracking_type: 追踪类型，用于区分不同的更新任务

    Returns:
        是否需要执行更新，异常则默认返回需要
    """
    try:
        with conn.cursor() as cursor:
            # 检查 tracking_value
            sql = """
                SELECT 
                    CASE 
                        WHEN tracking_value IS NULL THEN TRUE
                        WHEN UNIX_TIMESTAMP(NOW()) - UNIX_TIMESTAMP(tracking_value) > 86400 THEN TRUE
                        ELSE FALSE
                    END AS need_update
                FROM T_tracking_meta 
                WHERE tracking_key = %s 
                  AND tracking_type = %s;
            """
            cursor.execute(sql, [tracking_key, tracking_type])
            result = cursor.fetchone()
            if not result[0]:
                return False
            
            # 更新 tracking_value 值
            sql = """
                UPDATE T_tracking_meta 
                SET 
                    tracking_value = NOW() 
                WHERE tracking_key = %s 
                  AND tracking_type = %s;
            """
            cursor.execute(sql, [tracking_key, tracking_type])
    except Exception as e:
        conn.rollback()
        error_name = type(e).__name__
        logger.error(f"Database operation exception: {error_name}")
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )
        return False

    return True

def read_clan_cache(conn: Connection, clan_id: int) -> Optional[tuple]:
    """读取公会统计缓存数据

    从 T_clan_stats 表获取指定公会的赛季和队伍数据

    Args:
        conn: 数据库连接
        clan_id: 公会 ID

    Returns:
        包含 season 和 team_data 的元组，查询无结果时返回 None
    """
    try:
        with conn.cursor() as cursor:
            sql = """
                SELECT 
                    season, 
                    team_data 
                FROM T_clan_stats 
                WHERE clan_id = %s;
            """
            cursor.execute(sql, [clan_id])
            return cursor.fetchone()
    except Exception:
        logger.error(traceback.format_exc())

def update_clan_cache(
    conn: Connection,
    update_params: list,
    insert_data_list: list,
) -> None:
    """更新公会统计缓存并插入对战明细

    先更新 T_clan_stats 表的公会统计数据，再批量插入对战明细到赛季分表

    Args:
        conn: 数据库连接
        update_params: 更新参数列表
        insert_data_list: 对战明细插入数据列表，为空时跳过插入
    """
    try:
        
        with conn.cursor() as cursor:
            # 更新公会统计表
            update_sql = """
                UPDATE T_clan_stats
                SET
                    season = %s,
                    leading_team = %s,
                    battles = %s,
                    win_rate = %s,
                    public_rating = %s,
                    league = %s,
                    division = %s,
                    division_rating = %s,
                    max_streak = %s,
                    stage_type = %s,
                    stage_battles = %s,
                    stage_victories = %s,
                    stage_progress = %s,
                    team_data = %s,
                    last_battle_at = FROM_UNIXTIME(%s),
                    updated_at = NOW() 
                WHERE clan_id = %s
            """
            cursor.execute(update_sql, update_params)

            # 插入对战明细
            if insert_data_list:
                season_id = update_params[0]
                insert_sql = f"""
                    INSERT INTO S_clan_battle_{season_id} (
                        battle_time, clan_id, team_number, battle_result,
                        battle_rating, battle_stage, league, division,
                        division_rating, public_rating, stage_type, stage_progress
                    ) VALUES (
                        FROM_UNIXTIME(%s),%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s
                    );
                """
                cursor.executemany(insert_sql, insert_data_list)

            conn.commit()
    except Exception as e:
        conn.rollback()
        error_name = type(e).__name__
        logger.error(f"Database operation exception: {error_name}")
        write_exception(
            error_type="DatabaseError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )

def init_new_clans(cursor: Cursor, clans: list) -> None:
    """为新用户创建基础表记录"""

    if not clans:
        return
    # 1. 批量插入 T_clan_base
    values_list = []
    params = []
    for clan in clans:
        values_list.append("(%s, %s, %s)")
        params.extend([clan[0], clan[1], clan[2]])
    
    sql = f"INSERT INTO T_clan_base (clan_id, tag, league) VALUES {','.join(values_list)};"
    cursor.execute(sql, params)

    # 2. 批量插入所有子表
    for table_name in CLAN_INIT_TABLE_LIST:
        values_list = []
        params = []
        for clan in clans:
            values_list.append("(%s)")
            params.append(clan[0])
        
        sql = f"INSERT INTO {table_name} (clan_id) VALUES {','.join(values_list)};"
        cursor.execute(sql, params)

def get_update_ids(
    cursor: Cursor, 
    season_id: int, 
    clan_data_list: list
) -> list:
    """比较排行榜数据与数据库记录，返回需要更新的公会 ID 列表

    同时会为新公会初始化基础表和统计表记录

    Args:
        conn: 数据库连接
        season_id: 当前赛季 ID
        clan_data_list: 排行榜公会数据
    """
    update_ids = []
    # 批量查询已存在的公会记录，避免逐条查询
    clan_ids = [d[0] for d in clan_data_list]

    placeholders = ','.join(['%s'] * len(clan_ids))
    sql = f"""
        SELECT 
            clan_id, 
            season, 
            UNIX_TIMESTAMP(last_battle_at) 
        FROM T_clan_stats
        WHERE clan_id IN ({placeholders});
    """
    cursor.execute(sql, clan_ids)
    existing_map = {row[0]: row for row in cursor.fetchall()}
    missing_rows = []
    existing_rows = []
    for clan_data in clan_data_list:
        clan_id = clan_data[0]
        existing = existing_map.get(clan_id)

        if existing is None:
            missing_rows.append(clan_data)
            update_ids.append(clan_id)
        else:
            # 已有公会：比较 last_battle_at 和赛季是否变化
            existing_rows.append(clan_data)
            if clan_data[3] is None:
                continue
            if (
                existing[2] is None
                or existing[2] != clan_data[3]
                or existing[1] != season_id
            ):
                # 判断需要更新的条件
                # 1. 数据库中没有 last_battle_at 记录（首次统计到该工会）
                # 2. last_battle_at 时间戳不同（有新战斗发生）
                # 3. 赛季 ID 不同（新赛季首次获取数据）
                update_ids.append(clan_id)

    if existing_rows:
        # 批量更新
        update_sql = """
            UPDATE T_clan_base
            SET 
                tag = %s, 
                league = %s, 
                updated_at = NOW()
            WHERE clan_id = %s;
        """
        update_params = [
            [d[1], d[2], d[0]] for d in existing_rows
        ]
        cursor.executemany(update_sql, update_params)
    
    if missing_rows:
        init_new_clans(cursor, missing_rows)
        logger.info(f'Insert {len(missing_rows)} new clans')
    
    return update_ids

def get_clan_leaderboard(cursor: Cursor, clan_ids: list[str]):
    """根据用户ID列表，从数据库中批量读取排行榜数据"""
    placeholders = ','.join(['%s'] * len(clan_ids))
    sql = f"""
        SELECT 
            s.clan_id,
            b.tag,
            s.leading_team,
            s.battles,
            s.win_rate,
            s.league,
            s.division,
            s.public_rating, 
            s.max_streak,
            s.stage_type,
            s.stage_battles,
            s.stage_victories,
            s.stage_progress,
            UNIX_TIMESTAMP(s.last_battle_at)
        FROM T_clan_stats s
        LEFT JOIN T_clan_base b
            ON s.clan_id = b.clan_id
        WHERE s.clan_id IN ({placeholders});
    """
    cursor.execute(sql, clan_ids)
    rows = cursor.fetchall()
    result = {}

    for row in rows:
        clan_id = str(row[0])
        rating = row[7] + 0.1 * row[10] + 0.01 * row[11]
        result[clan_id] = [
            row[1], row[2], row[3], row[4], get_rating_level(row[4], 'win_rate'), 
            row[5], row[6], rating, row[8], row[9], 
            row[12], row[13]
        ]
    
    payload = []
    for i, user_id in enumerate(clan_ids):
        payload.append([i+1, int(user_id)] + result.get(user_id))

    return payload