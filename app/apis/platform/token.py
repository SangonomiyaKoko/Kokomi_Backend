from app.loggers import ExceptionLogger
from app.middlewares import RedisClient
from app.utils import TimeUtils
from app.network import ExternalAPI
from app.response import JSONResponse

class TokenAPI:
    @ExceptionLogger.handle_program_exception_async
    async def set_ac(account_id: int, access_token: str):
        """设置用户 Access-Token"""
        # 先验证用户当前确实处于隐藏战绩状态
        error, response = JSONResponse.extract_data(
            response=await ExternalAPI.get_user_basic(account_id)
        )
        if error:
            return response
        
        user_info = response.get(str(account_id))

        # 用户不存在(404 not found)
        if user_info is None:
            return JSONResponse.API_UserNotExist
        
        # 用户隐藏战绩
        if 'hidden_profile' not in user_info:
            return JSONResponse.API_InvalidAccessToken
        
        # 再验证传入 token 后用户能正常获取数据
        error, response = JSONResponse.extract_data(
            response=await ExternalAPI.get_user_basic(account_id, access_token)
        )
        if error:
            return response
        
        user_info = response.get(str(account_id))

        # 用户不存在(404 not found)
        if user_info is None:
            return JSONResponse.API_UserNotExist
        
        # 用户隐藏战绩
        if 'hidden_profile' in user_info:
            return JSONResponse.API_InvalidAccessToken
        
        # 设置 token
        redis_key = f"token:ac:{account_id}"
        return await RedisClient.set(redis_key, access_token)
    
    @ExceptionLogger.handle_program_exception_async
    async def set_auth(account_id: int, access_token: str, expires_at: int):
        redis_key = f"token:auth:{account_id}"
        vaildity = expires_at - TimeUtils.timestamp() - 60
        result = await RedisClient.set(redis_key,access_token,vaildity)
        return result
    
    @ExceptionLogger.handle_program_exception_async
    async def del_auth(account_id: int):
        """删除ac"""
        redis_key = f"token:auth:{account_id}"
        result = await RedisClient.drop(redis_key)
        return result
    
    @ExceptionLogger.handle_program_exception_async
    async def del_ac(account_id: int):
        """删除ac"""
        redis_key = f"token:ac:{account_id}"
        return await RedisClient.drop(redis_key)

