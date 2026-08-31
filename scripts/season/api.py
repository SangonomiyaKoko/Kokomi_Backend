import traceback
from redis import Redis
from requests import Session
from typing import Optional, Union

from logger import logger
from exception import write_exception
from utils import (
    get_current_iso_time,
    formtime_to_timestamp
)
from settings import CLAN_API


def fetch_data(session: Session, url: str) -> Union[dict, str]:
    """发送 GET 请求并解析 JSON 响应

    Args:
        url: 请求地址

    Returns:
        成功时返回解析后的 dict，失败时返回错误标识字符串（如 'HTTP_STATUS_404'）
    """
    try:
        resp = session.get(url, timeout=5)

        if resp.status_code == 200:
            return resp.json()
        
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

def fetch_clan_leagues(
    session: Session,
    redis_client: Redis, 
    realm: str, 
    league: str, 
    division: str
) -> Optional[list]:
    """获取指定联赛和分段的公会排行榜数据

    Args:
        redis_client: Redis 客户端
        realm: 服务器区域
        league: 联赛等级
        division: 分段

    Returns:
        公会数据列表，每项为 [clan_id, tag, league, last_battle_timestamp]
        请求失败时返回 None。
    """
    try:
        clan_data_list = []
        url = (
            f'{CLAN_API}/api/ladder/structure/'
            f'?realm={realm}&league={league}&division={division}&limit=1000'
        )
        response = fetch_data(session, url)

        error = record_http_metrics(redis_client, [response], [url])
        if error:
            return
        
        for temp_data in response:
            clan_data_list.append([
                temp_data['id'],
                temp_data['tag'],
                league,
                formtime_to_timestamp(temp_data['last_battle_at']),
                temp_data['season_number']
            ])
        
        return clan_data_list
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Fetch user data failed: {error_name}")
        write_exception(
            error_type="NetworkError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )

def fetch_clan_season(session: Session, redis_client: Redis, clan_id: int) -> Optional[dict]:
    """获取指定公会的当前赛季详情数据

    Args:
        redis_client: Redis 客户端，用于记录请求指标
        clan_id: 公会 ID

    Returns:
        公会当前赛季的 clanview 数据（含阶梯赛详情），失败时返回 None
    """
    try:
        url = f'{CLAN_API}/api/clanbase/{clan_id}/claninfo/'
        response = fetch_data(session, url)

        error = record_http_metrics(redis_client, [response], [url])
        if error:
            return
        
        return response
    except Exception as e:
        error_name = type(e).__name__
        logger.error(f"Fetch user data failed: {error_name}")
        write_exception(
            error_type="NetworkError",
            error_name=error_name,
            error_info=traceback.format_exc()
        )