from app.loggers import ExceptionLogger
from app.utils import GameUtils
from app.models import BotUserModel, PlatyerModel, PremiumModel
from app.network import ExternalAPI
from app.middlewares import RedisClient


class UserAPI:
    @ExceptionLogger.handle_program_exception_async
    async def get_base(region: str, account_id: int):
        # 获取用户的基本数据
        redis_key = f"token:ac:{account_id}"
        result = await RedisClient.get(redis_key)
        if result['code'] != 1000:
            return result
        if result['data']:
            ac = result['data'].get('ac')
        else:
            ac = None
        return await ExternalAPI.get_user_base(region, account_id, ac)
    
    @ExceptionLogger.handle_program_exception_async
    async def get_user_db_info(region: str, account_id: int):
        region_id = GameUtils.get_region_id(region)
        result = await PlatyerModel.get_user_brief(region_id, account_id)
        return result
    
    @ExceptionLogger.handle_program_exception_async
    async def get_user_premium_status(platform: str, user_id: int):
        result = await BotUserModel.premium_status(platform, user_id)
        return result
    
    @ExceptionLogger.handle_program_exception_async
    async def generate_code(max_use: int, validity: int, level: int, limit: int, describe: str = None):
        result = await PremiumModel.generate_code(
            max_use,
            validity,
            level,
            limit,
            describe
        )
        return result
