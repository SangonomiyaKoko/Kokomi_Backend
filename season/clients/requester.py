import traceback
from json import JSONDecodeError
from typing import Optional, Union

from redis import Redis
from requests import Session

from shard import RedisKeys, TimeUtils

from ..models import LeagueClanEntry
from ..logger import logger, write_exception
from ..settings import REQUEST_TIMEOUT

from .endpoints import EndpointRegistry


# 请求失败时返回错误标记字符串，成功时返回解析后的响应数据
FetchResponse = Union[dict, list, str]


class APIRequester:
    """从 Clan API 获取公会原始数据"""

    @classmethod
    def fetch_leagues(
        cls,
        session: Session,
        redis_client: Redis,
        realm: str,
        league: str,
        division: str
    ) -> Optional[list[LeagueClanEntry]]:
        """获取指定联赛和分段的公会排行榜数据

        请求失败时返回 None
        """
        url = EndpointRegistry.league_ranking(realm, league, division)
        response = cls._fetch_single(session, url)

        # 记录指标，响应为错误标记则整体视为失败
        error = cls._record_metrics(redis_client, [response], [url])
        if error:
            return None

        try:
            # 该口返回的数据为确定的 List 格式
            return [
                LeagueClanEntry.from_api(data, league) 
                for data in response
            ]
        except Exception as e:
            error_name = type(e).__name__
            error_id = write_exception(
                error_type="ParseError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            logger.error(
                f'{league}-{division} | ERROR - {error_name} - {error_id}'
            )
            return None

    @classmethod
    def fetch_clan_info(
        cls, 
        session: Session, 
        redis_client: Redis, 
        clan_id: int
    ) -> Optional[dict]:
        """获取指定公会的当前赛季详情数据

        请求失败时返回 None
        """
        url = EndpointRegistry.clan_info(clan_id)
        response = cls._fetch_single(session, url)

        # 记录指标，响应为错误标记则整体视为失败
        error = cls._record_metrics(redis_client, [response], [url])
        if error:
            return None

        return response

    @staticmethod
    def _fetch_single(
        session: Session, 
        url: str
    ) -> FetchResponse:
        """发送单个请求，返回解析后的响应或错误标记字符串"""
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                try:
                    return resp.json()
                except JSONDecodeError:
                    return "Game_API_Error"

            return f'HTTP_STATUS_{resp.status_code}'
        except Exception as e:
            return f'ERROR_{type(e).__name__}'

    @staticmethod
    def _record_metrics(
        redis_client: Redis,
        responses: list[FetchResponse],
        urls: list[str]
    ) -> Optional[str]:
        """记录 HTTP 指标，返回错误标记，无错误时返回 None"""
        error_count = 0
        error = None
        iso_time = TimeUtils.iso_time()

        # 检查所有的返回数据
        for i, response in enumerate(responses):
            if isinstance(response, str):
                logger.info(f'{response} {urls[i]}')
                error_count += 1
                error = response

        # 记录游戏 API 调用的统计数据
        incrby_keys = {
            RedisKeys.metrics('http', 'annual', iso_time.date_year): len(urls),
            RedisKeys.metrics('http', 'monthly', iso_time.date_month): len(urls),
            RedisKeys.metrics('http', 'daily:total', iso_time.date): len(urls)
        }
        if error_count > 0:
            incrby_keys.update({
                RedisKeys.metrics('http', 'daily:error', iso_time.date): error_count
            })

        try:
            pipe = redis_client.pipeline()
            for name, amount in incrby_keys.items():
                pipe.incrby(name, amount)
            pipe.execute()
        except Exception:
            logger.error('Failed to record HTTP metrics')

        return error
