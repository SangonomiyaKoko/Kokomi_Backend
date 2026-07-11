import httpx

from app.core import EnvConfig, api_logger
from app.response import JSONResponse, ResponseDict
from app.loggers import ExceptionLogger
from app.schemas import GameAPIException


TIMEOUT = httpx.Timeout(
    connect=2.0,
    read=10.0,
    write=3.0,
    pool=2.0
)

class HttpClient:
    """HTTP 异步客户端，用于调用各类游戏 API"""
    _client: httpx.AsyncClient = None

    @classmethod
    def init_client(cls) -> None:
        """初始化 HTTP 客户端，支持自定义 SSL 证书"""
        if EnvConfig.SSL_CA_BUNDLE:
            # 处理部分特殊地区服务器存在的SSL证书问题
            api_logger.info(f'Using local certificates: {EnvConfig.SSL_CA_BUNDLE}')
            cls._client = httpx.AsyncClient(
                timeout=TIMEOUT, 
                trust_env=False, 
                verify=EnvConfig.SSL_CA_BUNDLE
            )
        else:
            cls._client = httpx.AsyncClient(timeout=TIMEOUT, trust_env=False)
    
    @classmethod
    async def close_client(cls) -> None:
        """关闭 HTTP 客户端，释放连接资源"""
        if cls._client:
            await cls._client.aclose()
            cls._client = None

    @classmethod
    @ExceptionLogger.handle_network_exception_async
    async def get_user_data(cls, url: str) -> ResponseDict:
        """通过 VORTEX API 读取用户数据"""
        if cls._client is None:
            raise RuntimeError("HTTP client not initialized")
        
        response = await cls._client.get(url=url)
        request_code = response.status_code
        
        if request_code == 404:
            # 用户不存在或者账号删除的情况
            return JSONResponse.success({})
        elif request_code == 500:
            raise GameAPIException
        elif request_code == 200:
            # 正常返回值的处理
            request_result = response.json()
            if request_result.get('status') == 'ok':
                data = request_result['data']
                return JSONResponse.success(data)
            else:
                raise GameAPIException
        else:
            response.raise_for_status()  # 其他状态码

    @classmethod
    @ExceptionLogger.handle_network_exception_async
    async def get_clan_data(cls, url: str) -> ResponseDict:
        """通过 CLAN API 读取公会数据"""
        if cls._client is None:
            raise RuntimeError("HTTP client not initialized")
        
        response = await cls._client.get(url=url)
        request_code = response.status_code
        
        if request_code in [404, 503]:
            # 公会不存在或服务不可用
            return JSONResponse.success({})
        elif request_code == 500:
            raise GameAPIException
        elif request_code == 200:
            # 正常返回值的处理
            request_result = response.json()
            return JSONResponse.success(request_result)
        else:
            response.raise_for_status()  # 其他状态码

    @classmethod
    @ExceptionLogger.handle_network_exception_async
    async def get_official_data(cls, url: str) -> ResponseDict:
        """通过 OFFICIAL API 读取用户或公会数据"""
        if cls._client is None:
            raise RuntimeError("HTTP client not initialized")
        
        response = await cls._client.get(url=url)
        request_code = response.status_code
        request_result = response.json()
        
        if request_code == 200:
            return JSONResponse.success(request_result)
        elif request_code == 500:
            raise GameAPIException
        else:
            response.raise_for_status()  # 其他状态码