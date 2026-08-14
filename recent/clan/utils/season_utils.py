import json
from datetime import datetime, timezone, time

from settings import (
    REGION,
    DATA_DIR,
    CLAN_BATTLE_WINDOWS,
    METRIC_RATING_THRESHOLDS
)
from .time_utils import get_current_timestamp


def read_season_data() -> dict:
    """从本地 JSON 文件读取当前赛季配置数据"""
    # 俄服clan battle在s28后被rating战所替代
    # SEASON_ID, SEASON_FINISH, SEASON_START = 28, 1739944800, 1744005600
    file_path = DATA_DIR / f'json/clan_season.json'
    if not file_path.exists():
        return {"id": 0,"start": None,"finish": None}

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)
        return data

def refresh_season_data(season_id: int) -> dict:
    """刷新本地 JSON 文件中的当前赛季配置数据"""
    file_path = DATA_DIR / f'json/clan_season.json'
    data = {"id": season_id,"start": None,"finish": None}

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

def is_cb_active(season_start: int, season_finish: int) -> bool:
    """判断当前时间是否处于公会战活跃窗口内

    Args:
        season_start: 赛季开始时间戳
        season_finish: 赛季结束时间戳

    Returns:
        是否在活跃窗口内
    """
    # 没有配置赛季时间区间
    if not season_start or not season_finish:
        return False

    # 当前时间戳
    now_ts = get_current_timestamp()

    # 判断是否处于赛季工会战的开启时间内
    if not (season_start <= now_ts <= season_finish):
        return False

    now = datetime.fromtimestamp(now_ts, tz=timezone.utc)
    weekday = now.weekday()
    current_time = now.time()

    for start, end, regions in CLAN_BATTLE_WINDOWS[weekday]:
        if time(start[0], start[1]) <= current_time < time(end[0], end[1] + 29):
            if REGION in regions:
                return True

    return False

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
