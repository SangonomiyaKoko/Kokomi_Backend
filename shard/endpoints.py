import random


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

class Endpoints:
    
    @staticmethod
    def uid_rule(region: str) -> list:
        """服务器合法 UID 区间"""
        return _REGION_CONFIGS[region]['uid_rule']

    @staticmethod
    def clan_api(region: str) -> str:
        """官方 Clan API 地址"""
        return _REGION_CONFIGS[region]['clan_api']

    @staticmethod
    def official_api(region: str) -> str:
        """返回 Official 接口的 url 地址"""
        return _REGION_CONFIGS[region]['official_api']

    @staticmethod
    def vortex_api(region: str, config: tuple[str, list]) -> str:
        """基于代理配置文件返回 Vortex 接口的 url 地址"""
        vortex_api_url = _REGION_CONFIGS[region]['vortex_api']
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