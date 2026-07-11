from datetime import datetime, timezone

from settings import (
    DATE_FMT,
    METRIC_RATING_THRESHOLDS
)


def get_formatted_date() -> str:
    """获取当前日期格式化字符串，用于日志输出"""
    return datetime.now().strftime(DATE_FMT)

def get_current_timestamp() -> int:
    """获取当前 UTC 时间的 int 类型时间戳（秒）"""
    return int(datetime.now(timezone.utc).timestamp())

def get_current_iso_time() -> str:
    """获取当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def get_rating_level(
    value: float,
    metric_name: str
) -> int:
    """根据指标值计算对应的 Rating 等级

    将指标值与预设阈值列表对比，返回 1-8 的等级

    Args:
        value: 指标比值
        metric_name: 指标名称

    Returns:
        等级 1-8
    """
    # 获取对应指标的阈值列表
    thresholds = METRIC_RATING_THRESHOLDS.get(metric_name)
    if not thresholds:
        return 1

    # 遍历阈值，找到第一个大于 value 的阈值位置
    for i, threshold in enumerate(thresholds):
        if value < threshold:
            return i + 1  # 返回等级 (1-7)
    
    # 如果 value 大于等于所有阈值，返回最高等级 8
    return 8

def calc_ship_rating(ship_data: list, server_data: list | None):
    """计算玩家在单艘船上的综合 Rating

    Args:
        ship_data: 玩家数据 [win_rate(%), avg_damage, avg_frags]
        server_data: 服务器均值 [win_rate(%), avg_damage, avg_frags]

    Returns:
        (personal_rating, damage_rating, frags_rating)
    """
    if server_data is None:
        return -1, -1, -1
    
    # Step 1 - ratios:
    r_wins = ship_data[0] / server_data[0]
    r_dmg = ship_data[1] / server_data[1]
    r_frags = ship_data[2] / server_data[2]

    # Step 2 - normalization:
    n_wins = max(0, (r_wins - 0.7) / (1 - 0.7))
    n_dmg = max(0, (r_dmg - 0.4) / (1 - 0.4))
    n_frags = max(0, (r_frags - 0.1) / (1 - 0.1))

    # Step 3 - PR value:
    personal_rating = round(700 * n_dmg + 300 * n_frags + 150 * n_wins, 2)
    damage_rating = get_rating_level(r_dmg, 'damage')
    frags_rating = get_rating_level(r_frags, 'frags')
    
    return personal_rating, damage_rating, frags_rating