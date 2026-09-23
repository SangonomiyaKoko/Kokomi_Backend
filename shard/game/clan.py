from typing import Optional
from datetime import datetime, time, timezone

from ..utils.time import TimeUtils


# 各区服对应的公会战 realm 标识
CLAN_REALM_MAP = {
    "asia": "sg",
    "eu": "eu",
    "na": "us",
    "ru": "ru",
    "cn": "cn360"
}

class ClanColor:
    CLAN_COLOR_INDEX = {
        # user clan接口获取的颜色id对应的league
        13477119: 0,
        12511165: 1,
        14931616: 2,
        13427940: 3,
        13408614: 4,
        11776947: 5,
    }

    CLAN_COLOR_INDEX_2 = {
        # clan search接口获取的颜色hex对应的league
        '#cda4ff': 0,
        '#bee7bd': 1,
        '#e3d6a0': 2,
        '#cce4e4': 3,
        '#cc9966': 4,
        '#b3b3b3': 5
    }


class ClanPolicy:
    """公会活跃等级与更新间隔的策略配置"""

    # 计算工会活跃等级所用用户数量区间配置
    # 基于工会内用户数量，确定工会活跃度等级
    ACTIVITY_THRESHOLDS = [
        [10, 3],
        [30, 2],
        [50, 1]
    ]

    # 计算工会下次更新时间配置
    # 基于工会活跃等级，确定工会更新时间间隔
    NORMAL_STRATEGY = {
        "0-1": 21600,    # 6 HOURS
        "0-2": 43200,    # 12 HOURS
        "0-3": 93600     # 26 HOURS
    }

    # 公会战排行榜需要遍历的「联赛-分段」组合
    LEAGUE_LIST = [
        "0-1",
        "1-1", "1-2", "1-3",
        "2-1", "2-2", "2-3",
        "3-1", "3-2", "3-3",
        "4-1", "4-2", "4-3"
    ]


class ClanBattleUtils:
    """公会战时段判定相关公用函数

    本模块同时存在两套时段规则，二者服务于不同目的，不可互相替代：

    - `is_cb_active`（基于 CLAN_BATTLE_WINDOWS）按「联赛-分段」定义的对战
      窗口判断，供 Season 服务决定是否刷新公会战数据；
    - `cb_update_period`（基于服务器当地时间）按周一/四/五/日 01:00-05:00
      判断，供 Recent 服务定位「结束后更新」的结算时段。

    前者关心「对战是否正在进行」，后者关心「结算是否已经开始」。
    """

    # CLAN 模式开始时间窗口 (基于UTC时间)
    # CN: 19.30 ~ 23.30 UTC+8
    # SG: 19.30 ~ 23.30 UTC+8
    # EU: 19.00 ~ 23.00 UTC+1
    # NA: 19.30 ~ 23.30 UTC-5
    CLAN_BATTLE_WINDOWS = [
        [
            # [[开始时间],[结束时间],[对应服务器],人为定义的时间区间索引]
            [[0,30],  [4,30],  ["asia","eu","na"], 3]
        ],  # 周一
        [], # 周二未有时间窗口
        [
            [[11,30], [15,30], ["asia","eu","na","cn"], 1],
            [[18,0],  [22,0],  ["asia","eu","na"], 2]
        ],  # 周三
        [
            [[0,30],  [4,30],  ["asia","eu","na"], 3],
            [[11,30], [15,30], ["asia","eu","na","cn"], 1],
            [[18,0],  [22,0],  ["asia","eu","na"], 2]
        ],  # 周四
        [
            [[0,30],  [4,30],  ["asia","eu","na"], 3]
        ],  # 周五
        [
            [[11,30], [15,30], ["asia","eu","na","cn"], 1],
            [[18,0],  [22,0],  ["asia","eu","na"], 2]
        ],  # 周六
        [
            [[0,30],  [4,30],  ["asia","eu","na"], 3],
            [[11,30], [15,30], ["asia","eu","na","cn"], 1],
            [[18,0],  [22,0],  ["asia","eu","na"],2 ]
        ]   # 周末
    ]

    @staticmethod
    def get_window_index(
        region: str, timestamp: int
    ) -> Optional[int]:
        """返回指定时间戳落在哪个公会战时间区间

        区间索引由 CLAN_BATTLE_WINDOWS 人为定义；不在任何区间内时返回 None
        """
        moment = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        current_time = moment.time()

        windows = ClanBattleUtils.CLAN_BATTLE_WINDOWS[moment.weekday()]
        for start, end, regions, index in windows:
            if time(start[0], start[1]) <= current_time < time(end[0], end[1] + 29):
                if region in regions:
                    return index

        return None

    @staticmethod
    def is_cb_active(
        region: str, season_start: int, season_finish: int
    ) -> bool:
        """用于 Season 服务判断当前时间是否处于指定服务器的公会战活跃窗口内"""
        now_ts = TimeUtils.timestamp()
        # 如未配置 start 和 finish 字段则直接默认更新，避免数据丢失
        if (
            season_start and season_finish and
            not (season_start <= now_ts <= season_finish)
        ):
            # 当前时间不在赛季时间范围内
            return False

        moment = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        current_time = moment.time()

        windows = ClanBattleUtils.CLAN_BATTLE_WINDOWS[moment.weekday()]
        for start, end, regions, _ in windows:
            if time(start[0], start[1]) <= current_time < time(end[0], end[1] + 29):
                if region in regions:
                    return True

        return False

    @staticmethod
    def update_period(
        tz: int, season_start: Optional[int], season_finish: Optional[int]
    ) -> Optional[int]:
        """读取 CLAN 模式赛季信息，检测当前时间是否属于更新活跃时间段

        与 `is_cb_active` 是两套独立规则，详见类文档
        """
        now_ts = TimeUtils.timestamp()

        # 未配置 CLAN 模式活跃时间段时默认不活跃
        if not season_start or not season_finish:
            return None

        # 当前时间不在 CLAN 赛季时间范围内
        if not (season_start <= now_ts <= season_finish):
            return None

        # 转换为服务器当地时间
        local_ts = now_ts + tz * 3600
        dt = datetime.fromtimestamp(local_ts, tz=timezone.utc)

        # 周一 / 周四 / 周五 / 周日的 01:00–05:00 为更新活跃时间段
        if dt.isoweekday() not in (1, 4, 5, 7) or not (1 <= dt.hour < 5):
            return None

        # 当前活跃时间段的开始时间：当地时间当天 01:00
        period_start = dt.replace(
            hour=1,
            minute=0,
            second=0,
            microsecond=0,
        )

        # 转回 UTC Unix timestamp
        period_start_ts = int(
            period_start.timestamp() - tz * 3600
        )

        return period_start_ts


class ClanPolicyUtils:
    """基于 ClanPolicy 推导公会刷新间隔与活跃等级"""

    @staticmethod
    def clan_refresh_interval(activity_level: int) -> int:
        """基于公会活跃等级返回公会下次更新间隔（秒）"""
        return ClanPolicy.NORMAL_STRATEGY.get(
            f'0-{activity_level}',
            30 * 86400
        )

    @staticmethod
    def clan_activity_level(members: int) -> int:
        """基于公会成员数量返回公会活跃等级"""
        if members <= 0:
            return 0
        
        for threshold, level in ClanPolicy.ACTIVITY_THRESHOLDS:
            if members <= threshold:
                return level
        
        return 1
