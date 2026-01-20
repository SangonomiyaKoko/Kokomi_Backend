from app.loggers import ExceptionLogger
from app.middlewares import RedisClient
from app.schemas import ACResponse, AuthResponse
from app.utils import TimeUtils
from app.network import ExternalAPI
from app.response import JSONResponse

class TokenAPI:
    @ExceptionLogger.handle_program_exception_async
    async def set_ac(ac: ACResponse, region: str, platform: str = None, user_id: str = None):
        """
        设置ac
        """
        result = await ExternalAPI.varify_ac(region,ac.account_id,ac.access_token)
        if result['code'] != 1000:
            return result
        if result['data'] == False:
            return JSONResponse.API_2025_InvalidAccessToken
        redis_key = f"token:ac:{ac.account_id}"
        if platform:
            data = {
                'ac': ac.access_token,
                'platform': platform,
                'user_id': user_id
            }
        else:
            data = {
                'ac': ac.access_token
            }
        result = await RedisClient.set(redis_key,data)
        return result
    
    @ExceptionLogger.handle_program_exception_async
    async def set_auth_by_link(auth: AuthResponse, platform: str = None, user_id: str = None):
        redis_key = f"token:auth:{auth.account_id}"
        if platform:
            data = {
                'auth': auth.access_token,
                'platform': platform,
                'user_id': user_id
            }
        else:
            data = {
                'auth': auth.access_token
            }
        vaildity = auth.expires_at-TimeUtils.timestamp()
        result = await RedisClient.set(redis_key,data,vaildity)
        return result
    
    @ExceptionLogger.handle_program_exception_async
    async def del_auth(account_id: int):
        """
        删除ac
        """
        redis_key = f"token:auth:{account_id}"
        result = await RedisClient.drop(redis_key)
        return result
    
    @ExceptionLogger.handle_program_exception_async
    async def del_ac(account_id: int):
        """
        删除ac
        """
        redis_key = f"token:ac:{account_id}"
        result = await RedisClient.drop(redis_key)
        return result

