from pymysql.cursors import Cursor

from .logger import logger


def get_pvp_cache(cursor: Cursor, offset: int, batch_size: int):
    """分页获取 T_user_pvp 表中的 ship_cache 字段数据
    
    Args:
        cursor: 数据库游标对象
        offset: 查询起始偏移量
        batch_size: 每批查询的记录数
        
    Returns:
        查询到的记录列表，每条记录为包含 ship_cache 的元组
    """
    sql = """
        SELECT 
            cache 
        FROM T_user_cache 
        WHERE id BETWEEN %s AND %s;
    """
    cursor.execute(sql, [offset + 1, offset + batch_size])
    return cursor.fetchall()

def update_battles_stats_table(
    cursor: Cursor,
    battles_accum: dict[int, list[float]]
) -> None:
    """将场次平均统计数据批量更新到 T_ship_stats_by_battles 表
    
    Args:
        cursor: 数据库游标对象
        battles_accum: 字典，键为 ship_id，值为统计指标列表
            [battles, win_rate, avg_damage, avg_frags, avg_exp, 
             survived_rate, avg_scouting_damage, avg_potential_damage]
    """
    update_sql = """
        UPDATE T_ship_stats_by_battles
        SET
            battles               = %s,
            win_rate              = %s,
            avg_damage            = %s,
            avg_frags             = %s,
            avg_exp               = %s,
            survived_rate         = %s,
            avg_scouting_damage   = %s,
            avg_potential_damage  = %s,
            updated_at            = NOW()
        WHERE
            ship_id = %s;
    """
    params = []

    # 将累加数据与 ship_id 组合成参数列表
    for ship_id, acc in battles_accum.items():
        params.append(acc + [ship_id])

    if params:
        cursor.executemany(update_sql, params)
        logger.info(f"Updated {cursor.rowcount} rows in T_ship_stats_by_battles")

def update_users_stats_table(
    cursor: Cursor,
    users_accum: dict[int, list[float]]
) -> None:
    """将用户平均统计数据批量更新到 T_ship_stats_by_users 表
    
    Args:
        cursor: 数据库游标对象
        users_accum: 字典，键为 ship_id，值为统计指标列表
            [battles, users, rating, win_rate, avg_damage, avg_frags, 
             avg_exp, survived_rate, avg_scouting_damage, avg_potential_damage]
    """
    update_sql = """
        UPDATE T_ship_stats_by_users
        SET
            battles               = %s,
            users                 = %s,
            rating                = %s,
            win_rate              = %s,
            avg_damage            = %s,
            avg_frags             = %s,
            avg_exp               = %s,
            survived_rate         = %s,
            avg_scouting_damage   = %s,
            avg_potential_damage  = %s,
            updated_at            = NOW()
        WHERE
            ship_id = %s;
    """
    params = []

    # 将用户统计数据与 ship_id 组合成参数列表
    for ship_id, u in users_accum.items():
        params.append(u + [ship_id])

    if params:
        cursor.executemany(update_sql, params)
        logger.info(f"Updated {cursor.rowcount} rows in T_ship_stats_by_users")

def update_rating_distribution_table(
    cursor: Cursor,
    rating_percentiles: dict,
) -> None:
    """将 Rating 分布数据批量更新到 T_ship_rating_distribution 表
    
    Args:
        cursor: 数据库游标对象
        rating_percentiles: 字典，键为 ship_id，值为分布数据列表
            [sample_count, top1, top5, top10, top15, top50, top75, top90]
    """
    update_sql = """
        UPDATE T_ship_rating_distribution
        SET
            sample_count = %s,
            top1         = %s,
            top5         = %s,
            top10        = %s,
            top15        = %s,
            top50        = %s,
            top75        = %s,
            top90        = %s,
            updated_at   = NOW()
        WHERE
            ship_id = %s;
    """
    params = []

    # 将百分位数据与 ship_id 组合成参数列表
    for ship_id, pvals in rating_percentiles.items():
        params.append(pvals + [ship_id])

    if params:
        cursor.executemany(update_sql, params)
        logger.info(f"Updated {cursor.rowcount} rows in T_ship_rating_distribution")

def update_ship_pvp_stats(
    cursor: Cursor,
    update_data: list[tuple]
) -> None:
    """刷新 T_ship_pvp_stats 表中的统计数据
    
    使用 UPDATE 操作更新船只持有用户数和总场次
    
    Args:
        cursor: 数据库游标对象
        update_data: 待更新数据列表，每项为 [ship_users, total_battles, ship_id]
    """
    sql = """
        UPDATE T_ship_pvp_stats
        SET
            ship_users = %s,
            total_battles = %s
        WHERE ship_id = %s;
    """
    
    cursor.executemany(sql, update_data)
    logger.info(f"Updated {len(update_data)} rows in T_ship_pvp_stats")