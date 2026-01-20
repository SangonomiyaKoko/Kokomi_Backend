from app.loggers import ExceptionLogger
from app.network import ExternalAPI
from app.models import RecentModel, BotUserModel
from app.middlewares import RedisClient
from app.utils import TimeUtils
from app.response import JSONResponse


class RecentOverallAPI:
    @ExceptionLogger.handle_program_exception_async
    async def enable_recent(platform: str, user_id: str, region: str, account_id: int):
        """
        启用绑定账号的Recent功能

        先获取用户的premium信息再判断启用Recent还是RecentPro
        """
        redis_key = f"token:ac:{account_id}"
        result = await RedisClient.get(redis_key)
        if result['code'] != 1000:
            return result
        if result['data']:
            ac = result['data'].get('ac')
        else:
            ac = None
        result = await ExternalAPI.get_user_name(region, account_id, ac)
        if result['code'] != 1000:
            return result
        # recent功能需要: 1.用户存在且公开战绩 2.近一年内活跃
        # recentpro功能需要: 1.用户存在且公开战绩 2.近三个月活跃
        lbt = result['data']['last_battle_time']
        now_timestamp = TimeUtils.timestamp()
        premium_status = await BotUserModel.premium_status(platform, user_id)
        if premium_status['code'] != 1000:
            return premium_status 
        if (
            premium_status['data'] and 
            (len(premium_status['data']['users']) < premium_status['data']['level'])
        ):
            user_id = premium_status['data']['id']
            # Premium用户
            if lbt is None or now_timestamp - lbt > 90*24*60*60:
                return JSONResponse.API_2016_AccountNotEligible
            else:
                result = await RecentModel.enable_recent_pro(region, account_id, user_id, premium_status['data']['limit'])
                return result
        else:
            # 普通用户
            if lbt is None or now_timestamp - lbt > 360*24*60*60:
                return JSONResponse.API_2016_AccountNotEligible
            else:
                result = await RecentModel.enable_recent(region, account_id)
                return result
    
    
    @ExceptionLogger.handle_program_exception_async
    async def disable_recent(platform: str, user_id: str, region: str, account_id: int):
        """
        删除绑定账号的RecentPro功能
        """
        # recent功能需要: 1.用户存在且公开战绩 2.近一年内活跃
        # recentpro功能需要: 1.用户存在且公开战绩 2.近三个月活跃
        premium_status = await BotUserModel.premium_status(platform, user_id)
        if premium_status['code'] != 1000:
            return premium_status 
        if premium_status['data']:
            user_id = premium_status['data']['id']
            is_user = False
            for user in premium_status['data']['users']:
                if account_id == user[1]:
                    is_user = True
            if is_user == False:
                return JSONResponse.API_2021_RecentDataDeletionFailed
            else:
                return await RecentModel.disable_recent_pro(region, account_id, user_id)
        else:
            return JSONResponse.API_2018_ContactAuthorForDataDeletion