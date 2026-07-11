from app.core import EnvConfig
from app.response import JSONResponse
from app.loggers import ExceptionLogger
from app.models import UserStatsSyncer
from app.network import ExternalAPI


class BasicAPI:
    @ExceptionLogger.handle_program_exception_async
    async def get_user_basic(account_id: int, access_token: str = None):
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
            return JSONResponse.API_UserHiddenProfile
        
        # 用户没有战绩
        if (
            user_info is None or 
            'statistics' not in user_info or 
            'basic' not in user_info['statistics']
        ):
            return JSONResponse.API_UserDataIsNone
        
        if not EnvConfig.DEV_MODE:
            # 非开发模式下，刷新用户的数据库缓存数据
            error, refresh = JSONResponse.extract_data(
                response=await UserStatsSyncer.refresh(account_id, response)
            )
            if error:
                return refresh
        
        statistics = user_info['statistics']
        basic_data = statistics.get('basic', {})
        leveling_points = basic_data.get('leveling_points', 0)
        # 处理国服特殊账号
        if leveling_points >= 1_000_000:
            leveling_points -= 1_000_000
        
        # 用户没有战绩
        if leveling_points == 0:
            return JSONResponse.API_UserDataIsNone
        
        register_time = int(user_info.get('created_at', 0))
        
        user_basic = {
            'region': EnvConfig.REGION,
            'user_id': account_id,
            'username': user_info['name'],
            'karma': user_info.get('karma', 0),
            'created_at': register_time if register_time not in (0, None) else None,
            'clan': None,
            'insignias': user_info.get('dog_tag')
        }

        return JSONResponse.success(user_basic)