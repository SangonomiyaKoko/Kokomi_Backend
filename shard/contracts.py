import random


class ServicesName:
    """各服务的名称常量，同时用于日志名、状态键与服务配置的索引"""
    ACCOUNT = 'Account'
    CACHE = 'UserCache'
    RECENT = 'Recent'
    MEMBER = 'ClanMember'
    SEASON = 'ClanSeason'
    STATS = 'ServerStats'

    # Celery 不标记状态，而是通过消息挤压量判断健康度
    CELERY = 'Celery'

    @classmethod
    def to_list(cls) -> list[str]:
        """返回全部服务名称"""
        return [
            cls.ACCOUNT,
            cls.CACHE,
            cls.RECENT,
            cls.MEMBER,
            cls.SEASON,
            cls.STATS
        ]


class CommonConfig:
    """跨服务共用的任务名、队列名与建表清单"""

    REFRESH_TASK_NAME = 'user_refresh'
    REFRESH_QUEUE_NAME = 'refresh_queue'
    STATUS_FIELDS = [
        'overdue',
        'within_24h',
        'within_week',
        'within_month',
        'within_quarter'
    ]
    USER_INIT_TABLE_LIST = [
        "T_user_clan",
        "T_user_stats",
        "T_user_cache",
        "T_user_random",
        "T_user_ranked",
        "T_user_config"
    ]
    CLAN_INIT_TABLE_LIST = [
        "T_clan_users",
        "T_clan_stats",
        "T_clan_team"
    ]
    SHIP_INIT_TABLE_LIST = [
        "T_ship_pvp_stats",
        "T_ship_stats_by_battles",
        "T_ship_stats_by_users",
        "T_ship_rating_distribution"
    ]


class RedisKeys:
    """用于返回 Redis 键名"""

    @staticmethod
    def services(
        name: str
    ) -> str:
        return f"status:{name}"

    @staticmethod
    def metrics(
        name: str,
        index: str,
        date: str
    ) -> str:
        return f"metrics:{name}:{index}:{date}"

    @staticmethod
    def queue_lock(
        spaid: int
    ) -> str:
        """用于账号调度器与 Celery 刷新任务之间的入队锁"""
        return f"refresh_lock:queue:{spaid}"

    @staticmethod
    def insert_lock() -> str:
        """用于跨服务插入新用户时的互斥锁"""
        return "refresh_lock:insert"

    @staticmethod
    def recent_lock(
        spaid: int
    ) -> str:
        """用于 Recent 用户刷新分布式锁"""
        return f"refresh_lock:recent:{spaid}"

    @staticmethod
    def user_lock(
        spaid: int
    ) -> str:
        """用于用户刷新分布式锁"""
        return f"refresh_lock:user:{spaid}"

    @staticmethod
    def user_ac_token(
        spaid: int
    ) -> str:
        return f"token:ac:{spaid}"

    @staticmethod
    def clan_zrank() -> str:
        return "leaderboard:clan"


class Endpoints:
    """各服务器的接口地址与合法 UID 区间"""

    _REGION_CONFIGS = {
        "ru": {
            "uid_rule": [1, 499999999],
            "vortex_api": "https://vortex.korabli.su",
            "clan_api": "https://clans.korabli.su",
            "official_api": "https://api.korabli.su/mk"
        },
        "eu": {
            "uid_rule": [500000001, 999999999],
            "vortex_api": "https://vortex.worldofwarships.eu",
            "clan_api": "https://clans.worldofwarships.eu",
            "official_api": "https://api.worldofwarships.eu/wows"
        },
        "na": {
            "uid_rule": [1000000001, 1999999999],
            "vortex_api": "https://vortex.worldofwarships.com",
            "clan_api": "https://clans.worldofwarships.com",
            "official_api": "https://api.worldofwarships.com/wows"
        },
        "asia": {
            "uid_rule": [2000000001, 3999999999],
            "vortex_api": "https://vortex.worldofwarships.asia",
            "clan_api": "https://clans.worldofwarships.asia",
            "official_api": "https://api.worldofwarships.asia/wows"
        },
        "cn": {
            "uid_rule": [7000000001, 7999999999],
            "vortex_api": "https://vortex.wowsgame.cn",
            "clan_api": "https://clans.wowsgame.cn",
            "official_api": None
        }
    }

    @staticmethod
    def uid_rule(region: str) -> list:
        """服务器合法 UID 区间"""
        return Endpoints._REGION_CONFIGS[region]['uid_rule']

    @staticmethod
    def clan_api(region: str) -> str:
        """官方 Clan API 地址"""
        return Endpoints._REGION_CONFIGS[region]['clan_api']

    @staticmethod
    def official_api(region: str) -> str:
        """返回 Official 接口的 url 地址"""
        return Endpoints._REGION_CONFIGS[region]['official_api']

    @staticmethod
    def vortex_api(region: str, config: tuple[str, list]) -> str:
        """基于代理配置文件返回 Vortex 接口的 url 地址"""
        vortex_api_url = Endpoints._REGION_CONFIGS[region]['vortex_api']
        mode, points = config

        if mode == 'default':
            # 默认配置下直接调用 Vortex API
            return vortex_api_url
        elif len(points) <= 0:
            # 非默认配置下，PROXY_POINTS 必须有配置
            return vortex_api_url
        elif mode == 'direct':
            # 直连配置下直接返回第一个地址
            return points[0]
        elif mode == 'proxy':
            # 代理配置下从配置的地址+ Vortex API地址中随机选择
            return random.choice(points + [vortex_api_url])
        else:
            return vortex_api_url
