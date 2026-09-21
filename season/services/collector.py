import json

from shard import (
    ClanPolicy,
    CLAN_REALM_MAP,
    RedisKeys,
    progress_iterable
)

from ..core import RunContext
from ..clients import APIRequester
from ..logger import logger
from ..settings import DATA_DIR, REGION


def refresh_season_data(season_id: int) -> None:
    """刷新本地 JSON 文件中的当前赛季配置数据

    新赛季的起止时间未知，一并重置为 None，等待人工补录
    """
    file_path = DATA_DIR / 'json/clan_season.json'
    data = {"id": season_id, "start": None, "finish": None}

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


class LeagueCollector:
    """遍历所有联赛分段，收集公会排行榜数据"""

    @classmethod
    def main(cls, run_ctx: RunContext) -> bool:
        """收集排行榜数据，返回是否成功获取到数据"""
        entries = []
        league_counts = {}
        _existing_ids = set() # 去重用

        logger.enable_tqdm()
        try:
            for league_division in progress_iterable(
                items=ClanPolicy.LEAGUE_LIST,
                entry='league',
                logger=logger
            ):
                league, division = league_division.split('-')
                league_data = APIRequester.fetch_leagues(
                    session=run_ctx.session,
                    redis_client=run_ctx.redis_client,
                    realm=CLAN_REALM_MAP.get(REGION),
                    league=league,
                    division=division
                )
                if league_data is None:
                    logger.info(f'{league_division} | Failed to obtain data')
                    continue

                if not league_data:
                    continue

                # 读取该次请求中的赛季 ID
                latest_season_id = league_data[0].season_id

                # 赛季变化处理
                if latest_season_id != run_ctx.season_id:
                    # 首次遇到新赛季，更新本地赛季配置
                    logger.info(
                        'Clan battle season changed: %s -> %s',
                        run_ctx.season_id, latest_season_id
                    )
                    if entries:
                        return False
                    
                    run_ctx.season_id = latest_season_id
                    refresh_season_data(latest_season_id)
                    run_ctx.redis_client.delete(RedisKeys.clan_zrank())

                league_counts[league] = (
                    league_counts.get(league, 0) + len(league_data)
                )
                # ID 去重
                for entry in league_data:
                    if entry.clan_id not in _existing_ids:
                        _existing_ids.add(entry.clan_id)
                        entries.append(entry)
        finally:
            logger.disable_tqdm()

        logger.info(
            'Current active clans: %s',
            ', '.join(f'{key}({value})' 
            for key, value in sorted(
                league_counts.items())
            )
        )

        run_ctx.clan_entries = entries
        run_ctx.league_counts = league_counts

        return True
