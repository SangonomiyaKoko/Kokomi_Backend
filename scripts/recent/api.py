import random
import asyncio
import traceback
from redis import Redis
from httpx import AsyncClient
from typing import Optional, Union

from logger import logger
from exception import write_exception
from utils import get_current_iso_time
from settings import VORTEX_API


async def fetch_data(async_client: AsyncClient, url: str):
    """发送 GET 请求并解析 JSON 响应

    Args:
        async_client: HTTP 异步客户端
        url: 请求地址

    Returns:
        成功时返回解析后的 dict，失败时返回错误标识字符串（如 'HTTP_STATUS_404'）
    """
    try:
        resp = await async_client.get(url)

        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'ok':
                return data.get('data', {})
            else:
                return "Game_API_Error"
        elif resp.status_code == 404:
            return {}
        
        return f'HTTP_STATUS_{resp.status_code}'
    except Exception as e:
        return f'ERROR_{type(e).__name__}'

def record_http_metrics(
    redis_client: Redis, 
    responses: list[Union[dict, str]],
    urls: list[str]
) -> Optional[str]:
    """记录 HTTP 请求指标到 Redis

    如果有多个 Error 则返回最后一个 Error 的信息

    Args:
        redis_client: Redis 客户端
        responses: fetch_data 返回结果列表
        urls: 对应请求的 URL 列表，用于日志输出

    Returns:
        错误字符串，全部成功则返回 None
    """
    error_count = 0
    error = None

    today = get_current_iso_time()[:10]

    # 检查所有的返回数据
    for i, response in enumerate(responses):
        if isinstance(response, str):
            logger.info(f'{response} {urls[i]}')
            error_count += 1
            error = response
    
    # 记录游戏 API 调用的统计数据
    try:
        redis_client.incrby(f'metrics:http:annual:{today[:4]}', len(urls))
        redis_client.incrby(f'metrics:http:monthly:{today[:7]}', len(urls))
        redis_client.incrby(f'metrics:http:daily:total:{today}', len(urls))

        if error_count > 0:
            redis_client.incrby(f'metrics:http:daily:error:{today}', error_count)
    except Exception:
        logger.warning('Failed to record HTTP metrics')

    return error

async def fetch_user_recent_data(
    async_client: AsyncClient,
    redis_client: Redis,
    account_id: int
) -> Optional[list[Union[dict, str]]]:
    """获取用户的三个接口数据（基本信息、船只统计、PvP 详细）

    Args:
        async_client: HTTP 客户端
        redis_client: Redis 客户端（用于指标记录和 token 获取）
        account_id: 用户 ID

    Returns:
        成功时返回 [basic_data, ships_data] 响应
        失败时返回 None
    """
    try:
        redis_key = f"token:ac:{account_id}"
        ac = redis_client.get(redis_key)

        base_url = random.choice(VORTEX_API)

        urls = [
            f'{base_url}/api/accounts/{account_id}/' + (f'?ac={ac}' if ac else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_solo/' + (f'?ac={ac}' if ac else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div2/' + (f'?ac={ac}' if ac else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div3/' + (f'?ac={ac}' if ac else ''),
            f'{base_url}/api/accounts/{account_id}/ships/rank_solo/' + (f'?ac={ac}' if ac else '')
        ]

        tasks = [fetch_data(async_client, url) for url in urls]
        responses = await asyncio.gather(*tasks)

        # 统计 API 请求的指标
        error = record_http_metrics(redis_client, responses, urls)
        if error:
            return

        return responses
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Fetch user data failed: {error_name}")
        write_exception(
            error_type="NetworkError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )