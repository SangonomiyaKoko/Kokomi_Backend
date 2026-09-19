import traceback
from redis import Redis
from requests import Session
from typing import Optional, Union

from json import JSONDecodeError
from shard import (
    Endpoints,
    RedisKeys,
    TimeUtils
)

from .logger import logger, write_exception
from .settings import (
    REGION,
    REQUEST_TIMEOUT
)


class APIRequester:
    """从 API 获取工会原始数据"""

    @classmethod
    def fetch(
        cls,
        redis_client: Redis,
        session: Session,
        clan_id: int
    ) -> Optional[list]:
        """获取指定公会的成员列表"""
        try:
            base_url = Endpoints.clan_api(REGION)
            url = f'{base_url}/api/members/{clan_id}/'
            response = cls._fetch_single(session, url)

            # 记录指标，响应为错误标记则整体视为失败
            error = cls._record_metrics(
                redis_client=redis_client, 
                responses=[response], 
                urls=[url]
            )
            if error:
                return None

            return response
        except Exception as e:
            error_name = type(e).__name__
            error_id = write_exception(
                error_type="NetworkError",
                error_name=error_name,
                error_info=traceback.format_exc()
            )
            logger.error(f'{clan_id} | ERROR - {error_name} - {error_id}')
            return None

    @staticmethod
    def _fetch_single(
        session: Session, url: str
    ) -> Union[list, str]:
        """发送单个请求，返回 list 数据或错误标记字符串"""
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except JSONDecodeError:
                    return "Game_API_Error"
                
                if data.get('status') == 'ok':
                    return data['items']

                return 'Game_API_Error'
            return f'HTTP_STATUS_{resp.status_code}'
        except Exception as e:
            return f'ERROR_{type(e).__name__}'

    @staticmethod
    def _record_metrics(
        redis_client: Redis,
        responses: list[Union[list, str]],
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
            RedisKeys.metrics('http','annual',iso_time.date_year): len(urls),
            RedisKeys.metrics('http','monthly',iso_time.date_month): len(urls),
            RedisKeys.metrics('http','daily:total',iso_time.date): len(urls)
        }
        if error_count > 0:
            incrby_keys.update({
                RedisKeys.metrics('http','daily:error',iso_time.date): error_count
            })

        try:
            pipe = redis_client.pipeline()
            for name, amount in incrby_keys.items():
                pipe.incrby(name, amount)
            pipe.execute()
        except Exception:
            logger.error('Failed to record HTTP metrics')

        return error