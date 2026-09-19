from datetime import datetime, time, timezone

from .time_utils import TimeUtils


class GameUtils:
    CLAN_REALM_MAP = {
        "asia": "sg",
        "eu": "eu",
        "na": "us",
        "ru": "ru",
        "cn": "cn360"
    }

    #  定义接口字段对应的 ID
    SHIP_TYPE_MAP = {
        "AirCarrier": 1,
        "Battleship": 2,
        "Cruiser": 3,
        "Destroyer": 4,
        "Submarine": 5
    }
    SHIP_NATION_MAP = {
        "usa": 1,
        "japan": 2,
        "germany": 3,
        "uk": 4,
        "ussr": 5,
        "france": 6,
        "italy": 7,
        "pan_asia": 8,
        "europe": 9,
        "netherlands": 10,
        "commonwealth": 11,
        "pan_america": 12,
        "spain": 13
    }
    SHIP_RARITY_MAP = {
        "Common": 1,
        "Uncommon": 2,
        "Rare": 3,
        "Epic": 4,
        "Legendary": 5
    }
    SHIP_METRIC_MAP = {
        "battles": 1,
        "wins": 2,
        "damage": 3,
        "frags": 4,
        "exp": 5,
        "survived": 6,
        "scouting_dmg": 7,
        "potential_dmg": 8,
        "planes": 9,
        "rating": 10
    }

    # CLAN 模式开始时间窗口 (基于UTC时间)
    # SG: 19.30 ~ 23.30 UTC+8
    # EU: 19.00 ~ 23.00 UTC+1
    # NA: 19.30 ~ 23.30 UTC-5
    CLAN_BATTLE_WINDOWS = [
        [
            [[0,30],  [4,30],  ["asia","eu","na"]]
        ],
        [], # 周二未有时间窗口
        [
            [[11,30], [15,30], ["asia","eu","na","cn"]],
            [[18,0],  [22,0],  ["asia","eu","na"]]
        ],
        [
            [[0,30],  [4,30],  ["asia","eu","na"]],
            [[11,30], [15,30], ["asia","eu","na","cn"]],
            [[18,0],  [22,0],  ["asia","eu","na"]]
        ],
        [
            [[0,30],  [4,30],  ["asia","eu","na"]]
        ],
        [
            [[11,30], [15,30], ["asia","eu","na","cn"]],
            [[18,0],  [22,0],  ["asia","eu","na"]]
        ],
        [
            [[0,30],  [4,30],  ["asia","eu","na"]],
            [[11,30], [15,30], ["asia","eu","na","cn"]],
            [[18,0],  [22,0],  ["asia","eu","na"]]
        ]
    ]

    @staticmethod
    def is_cb_active(
        region: str, season_start: int, season_finish: int
    ) -> bool:
        """用于 Season 服务判断当前时间是否处于指定服务器的公会战活跃窗口内"""
        now_ts = TimeUtils.timestamp()
        if (
            season_start and season_finish and
            not (season_start <= now_ts <= season_finish)
        ):
            # 当前时间不在赛季时间范围内
            return False

        now = datetime.fromtimestamp(now_ts, tz=timezone.utc)
        current_time = now.time()

        for start, end, regions in GameUtils.CLAN_BATTLE_WINDOWS[now.weekday()]:
            if time(start[0], start[1]) <= current_time < time(end[0], end[1] + 29):
                if region in regions:
                    return True

        return False