import random
import asyncio
from typing import Optional, Union, Any, List

from app.loggers import ExceptionLogger
from app.utils import TimeUtils
from app.core import EnvConfig, api_logger
from app.middlewares import ServiceMetrics
from app.response import JSONResponse, ResponseDict

from .client import HttpClient



async def record_http_metrics(
    responses: list[ResponseDict],
    urls: list[str]
) -> Union[tuple[bool, ResponseDict], tuple[bool, list[Any]]]:
    """记录 HTTP 请求指标到 Redis
    
    如果有多个 Error 则返回最后一个 Error 的信息

    Args:
        responses: fetch_data 返回结果列表
        urls: 请求的 URL 列表

    Returns:
        tuple: (是否有错误, 错误信息或成功结果列表)
    """
    results = []
    error_count = 0
    error = None

    for i, response in enumerate(responses):
        if response.get('code') != 1000:
            api_logger.warning(f"{response.get('message')} {urls[i]}")
            error_count += 1
            error = response
        else:
            results.append(response.get('data', {}))
        
    today = TimeUtils.now_iso()[:10]
    await ServiceMetrics.http_incrby(today, len(urls))

    if error_count:
        await ServiceMetrics.http_error_incrby(today, error_count)
        return True, error
    else:
        return False, results

class DemoExternalAPI:
    """测试用API"""

    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_basic(account_id: int, user_token: Optional[str]) -> ResponseDict:
        """请求获取用户的基本数据"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)

        url = f'{base_url}/api/accounts/{account_id}/' + (f'?ac={user_token}' if user_token else '')
        response = await HttpClient.get_user_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_clan(account_id: int) -> ResponseDict:
        """获取用户所在公会信息"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        
        url = f'{base_url}/api/accounts/{account_id}/clans/'
        response = await HttpClient.get_user_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_clan_basic(clan_id: int) -> ResponseDict:
        """获取公会基本信息"""
        endpoints = EnvConfig.get_endpoints()
        base_url = endpoints.CLAN_API

        url = f'{base_url}/api/clanbase/{clan_id}/claninfo/'
        response = await HttpClient.get_clan_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_clan_users(clan_id: int) -> ResponseDict:
        """获取公会成员列表"""
        endpoints = EnvConfig.get_endpoints()
        base_url = endpoints.CLAN_API

        url = f'{base_url}/api/members/{clan_id}/'
        response = await HttpClient.get_clan_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])
       
class ExternalAPI:
    """外部 API 客户端"""

    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_search(nickname: str):
        """通过用户昵称搜索用户账号"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        
        url = f'{base_url}/api/accounts/search/{nickname.lower()}/'
        response = await HttpClient.get_user_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_clan_search(tag: str):
        """通过公会标签搜索公会"""
        endpoints = EnvConfig.get_endpoints()
        base_url = endpoints.CLAN_API

        url = f'{base_url}/api/search/autocomplete/?search={tag.lower()}&type=clans'
        response = await HttpClient.get_clan_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0].get('search_autocomplete_result', []))

    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_refresh(account_id: int, user_token: Optional[str]):
        """读取用户基本信息和所在公会信息"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        urls = [
            f'{base_url}/api/accounts/{account_id}/' + (f'?ac={user_token}' if user_token else ''),
            f'{base_url}/api/accounts/{account_id}/clans/'
        ]
        tasks = []
        responses = []
        async with asyncio.Semaphore(len(urls)):
            for url in urls:
                tasks.append(HttpClient.get_user_data(url))
            responses = await asyncio.gather(*tasks)

        error, results = await record_http_metrics(responses, urls)
        if error:
            return results
        
        return JSONResponse.success(results)

    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_basic(account_id: int, user_token: Optional[str]):
        """读取用户基本信息"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        url = f'{base_url}/api/accounts/{account_id}/' + (f'?ac={user_token}' if user_token else '')
        response = await HttpClient.get_user_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])
        
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_pve(account_id: int, user_token: Optional[str]):
        """获取用户 PvE 模式的船只数据"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        url = f'{base_url}/api/accounts/{account_id}/ships/pve/' + (f'?ac={user_token}' if user_token else '')
        response = await HttpClient.get_user_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])

    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_pvp_overall(account_id: int, user_token: Optional[str]):
        """获取用户所有 PvP 模式的船只数据（包含单排、双排、三排）"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        urls = [
            f'{base_url}/api/accounts/{account_id}/ships/pvp_solo/' + (f'?ac={user_token}' if user_token else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div2/' + (f'?ac={user_token}' if user_token else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div3/' + (f'?ac={user_token}' if user_token else '')
        ]
        tasks = []
        responses = []
        async with asyncio.Semaphore(len(urls)):
            for url in urls:
                tasks.append(HttpClient.get_user_data(url))
            responses = await asyncio.gather(*tasks)

        error, results = await record_http_metrics(responses, urls)
        if error:
            return results
        
        return JSONResponse.success(results)
        
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_pvp_field(account_id: int, field: str, user_token: Optional[str]):
        """获取用户指定 PvP 模式的船只数据"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        url = f'{base_url}/api/accounts/{account_id}/ships/pvp_{field}/' + (f'?ac={user_token}' if user_token else '')
        response = await HttpClient.get_user_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])
        
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_ranked(account_id: int, user_token: Optional[str]):
        """获取用户排位赛模式的船只数据"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        url = f'{base_url}/api/accounts/{account_id}/ships/rank_solo/' + (f'?ac={user_token}' if user_token else '')
        response = await HttpClient.get_user_data(url)

        error, results = await record_http_metrics([response], [url])
        if error:
            return results
        
        return JSONResponse.success(results[0])

    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_recent(account_id: int, user_token: Optional[str]):
        """获取用于用户 Recent 服务更新所需的数据"""
        endpoints = EnvConfig.get_endpoints()
        base_url = random.choice(endpoints.VORTEX_API)
        urls = [
            f'{base_url}/api/accounts/{account_id}/' + (f'?ac={user_token}' if user_token else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_solo/' + (f'?ac={user_token}' if user_token else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div2/' + (f'?ac={user_token}' if user_token else ''),
            f'{base_url}/api/accounts/{account_id}/ships/pvp_div3/' + (f'?ac={user_token}' if user_token else ''),
            f'{base_url}/api/accounts/{account_id}/ships/rank_solo/' + (f'?ac={user_token}' if user_token else '')
        ]
        tasks = []
        responses = []
        async with asyncio.Semaphore(len(urls)):
            for url in urls:
                tasks.append(HttpClient.get_user_data(url))
            responses = await asyncio.gather(*tasks)

        error, results = await record_http_metrics(responses, urls)
        if error:
            return results
        
        return JSONResponse.success(results)