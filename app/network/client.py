import httpx

from .response import JSONResponse
from .exception import handle_network_exception_async
from app.core import api_logger


REQUEST_TIMEOUT = 5

class HttpClient:
    """负责和外部API交互"""
    @handle_network_exception_async
    async def get_user_search(url):
        # 请求获取工会名称搜索结果
        async with httpx.AsyncClient() as client:
            res = await client.get(url=url, timeout = REQUEST_TIMEOUT)
            requset_code = res.status_code
            requset_result: dict = res.json()
            if requset_code == 200:
                data = requset_result.get('data', [])
                return JSONResponse.get_success_response(data)
            if requset_code in [400, 500, 503]:
                # 用户搜索接口还可能的返回值，主要是国服相关接口不支持模糊搜索导致的
                return JSONResponse.get_success_response([])
            else:
                api_logger.warning(f"Code{requset_code} {url}")
                res.raise_for_status()  # 其他状态码

    @handle_network_exception_async
    async def get_clan_search(url):
        # 请求获取工会名称搜索结果
        async with httpx.AsyncClient() as client:
            res = await client.get(url=url, timeout = REQUEST_TIMEOUT)
            requset_code = res.status_code
            requset_result: dict = res.json()
            if requset_code == 200:
                data = requset_result.get('search_autocomplete_result', [])
                return JSONResponse.get_success_response(data)
            else:
                api_logger.warning(f"Code{requset_code} {url}")
                res.raise_for_status()  # 其他状态码

    @handle_network_exception_async
    async def get_vehicles(url):
        # 请求获取vehicles数据
        async with httpx.AsyncClient() as client:
            res = await client.get(url=url, timeout=REQUEST_TIMEOUT)
            requset_code = res.status_code
            requset_result: dict = res.json()
            if requset_code == 200:
                data = requset_result.get('data', {})
                return JSONResponse.get_success_response(data)
            else:
                api_logger.warning(f"Code{requset_code} {url}")
                res.raise_for_status()  # 其他状态码

    @handle_network_exception_async
    async def get_game_version(url):
        # 请求获取vehicles数据
        async with httpx.AsyncClient() as client:
            body = [{"query":"query Version {\n  version\n}"}]
            res = await client.post(url=url, json=body, timeout=REQUEST_TIMEOUT)
            requset_code = res.status_code
            requset_result: dict = res.json()
            if requset_code == 200:
                return JSONResponse.get_success_response(requset_result)
            else:
                api_logger.warning(f"Code{requset_code} {url}")
                res.raise_for_status()  # 其他状态码

    @handle_network_exception_async
    async def get_user_data(url):
        async with httpx.AsyncClient() as client:
            res = await client.get(url=url, timeout=REQUEST_TIMEOUT)
            requset_code = res.status_code
            requset_result = res.json()
            if requset_code == 404:
                # 用户不存在或者账号删除的情况
                return JSONResponse.API_1000_Success
            elif requset_code == 200:
                # 正常返回值的处理
                data = requset_result['data']
                return JSONResponse.get_success_response(data)
            else:
                api_logger.warning(f"Code{requset_code} {url}")
                res.raise_for_status()  # 其他状态码

    @handle_network_exception_async
    async def get_offical_user_data(url):
        async with httpx.AsyncClient() as client:
            res = await client.get(url=url, timeout=REQUEST_TIMEOUT)
            requset_code = res.status_code
            requset_result = res.json()
            if requset_code == 200:
                if requset_result['status'] == 'error':
                    return JSONResponse.API_1000_Success
                return JSONResponse.get_success_response(requset_result)
            else:
                api_logger.warning(f"Code{requset_code} {url}")
                res.raise_for_status()  # 其他状态码