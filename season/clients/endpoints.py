from shard import Endpoints

from ..settings import REGION


class EndpointRegistry:
    """Clan API 的接口地址注册表"""

    @staticmethod
    def league_ranking(
        realm: str, league: str, division: str
    ) -> str:
        """指定联赛与分段的公会排行榜接口"""
        base_url = Endpoints.clan_api(REGION)

        return (
            f'{base_url}/api/ladder/structure/'
            f'?realm={realm}&league={league}&division={division}&limit=1000'
        )

    @staticmethod
    def clan_info(clan_id: int) -> str:
        """公会详情接口"""
        base_url = Endpoints.clan_api(REGION)

        return f'{base_url}/api/clanbase/{clan_id}/claninfo/'
