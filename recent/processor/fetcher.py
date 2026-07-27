import random
import asyncio
import traceback
from redis import Redis
from httpx import AsyncClient
from typing import Optional, Union

from loggers import logger, write_exception
from utils import TimeUtils
from context import UpdateContext
from settings import VORTEX_API


class UserDataFetcher:
    """从API获取用户原始数据"""

    @classmethod
    async def fetch_all(cls, ctx: UpdateContext) -> Optional[list]:
        """获取用户所有数据"""
        try:
            redis_key = f"token:ac:{ctx.account_id}"
            ac = ctx.redis_client.get(redis_key)
            
            base_url = random.choice(VORTEX_API)
            query = f'?ac={ac}' if ac else ''
            
            urls = [
                f'{base_url}/api/accounts/{ctx.account_id}/{query}',
                f'{base_url}/api/accounts/{ctx.account_id}/ships/pvp_solo/{query}',
                f'{base_url}/api/accounts/{ctx.account_id}/ships/pvp_div2/{query}',
                f'{base_url}/api/accounts/{ctx.account_id}/ships/pvp_div3/{query}',
                f'{base_url}/api/accounts/{ctx.account_id}/ships/rank_solo/{query}',
            ]
            
            tasks = [cls._fetch_single(ctx.async_client, url) for url in urls]
            responses = await asyncio.gather(*tasks)
            
            # 记录指标
            error = cls._record_metrics(ctx.redis_client, responses, urls)
            if error:
                return None
            
            return responses
            
        except Exception as e:
            error_name = type(e).__name__
            logger.error(f"Fetch user data failed: {error_name}")
            write_exception(
                error_type="NetworkError",
                error_name=error_name,
                error_info=traceback.format_exc(),
            )
            return None

    @staticmethod
    def _record_metrics(redis_client: Redis, responses: list, urls: list) -> Optional[str]:
        """记录HTTP指标"""
        error_count = 0
        error = None
        today = TimeUtils.get_current_iso_time()[:10]
        
        for i, response in enumerate(responses):
            if isinstance(response, str):
                logger.info(f'{response} {urls[i]}')
                error_count += 1
                error = response
        
        try:
            redis_client.incrby(f'metrics:http:annual:{today[:4]}', len(urls))
            redis_client.incrby(f'metrics:http:monthly:{today[:7]}', len(urls))
            redis_client.incrby(f'metrics:http:daily:total:{today}', len(urls))
            
            if error_count > 0:
                redis_client.incrby(f'metrics:http:daily:error:{today}', error_count)
        except Exception:
            logger.warning('Failed to record HTTP metrics')
        
        return error

    @staticmethod
    async def _fetch_single(async_client: AsyncClient, url: str) -> Union[dict, str]:
        """发送单个请求"""
        try:
            resp = await async_client.get(url)
            
            if resp.status_code == 200:
                data = resp.json()
                if data.get('status') == 'ok':
                    return data.get('data', {})
                return "Game_API_Error"
            elif resp.status_code == 404:
                return {}
            
            return f'HTTP_STATUS_{resp.status_code}'
        except Exception as e:
            return f'ERROR_{type(e).__name__}'
