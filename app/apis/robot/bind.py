from app.loggers import ExceptionLogger
from app.middlewares import RedisClient
from app.response import JSONResponse
from app.models import BotUserModel, PremiumModel
from app.utils import GameUtils
from app.network import ExternalAPI
from app.schemas import BindBody


class BindAPI:
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def getBind(platform: str, user_id: str):
        redis_key = f"bot_bind:{platform}:{user_id}"
        result = await RedisClient.get(redis_key)
        if result['code'] != 1000:
            return result
        if result['data']:
            if result['data'] == {}:
                return JSONResponse.API_1000_Success
            else:
                return JSONResponse.get_success_response(result['data'])
        result = await BotUserModel.get_user_bind(platform, user_id)
        if result['code'] != 1000:
            return result
        if result['data'] != None:
            await RedisClient.set(redis_key, result['data'], 7*24*60*60)
        return JSONResponse.get_success_response(result['data'])
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def getBindList(platform: str, user_id: str):
        result = await BotUserModel.get_user_bind_list(platform, user_id)
        return result
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def delBind(platform: str, user_id: str, del_index: int):
        # 先删除
        result = await BotUserModel.del_user_bind(platform, user_id, del_index)
        if result['code'] == 2012:
            # 刷新缓存
            redis_key = f"bot_bind:{platform}:{user_id}"
            await RedisClient.set(redis_key, {}, 7*24*60*60)
        return result
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def switchBind(platform: str, user_id: str, switch_index: int):
        result = await BotUserModel.switch_user_bind(platform, user_id, switch_index)
        if result['code'] == 1000:
            redis_key = f"bot_bind:{platform}:{user_id}"
            await RedisClient.set(redis_key, result['data'], 7*24*60*60)
        return result
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def postBind(platform: str, user_id: str, bind_data: BindBody):
        if bind_data.type == 'uid':
            redis_key = f"token:ac:{bind_data.uid}"
            result = await RedisClient.get(redis_key)
            if result['code'] != 1000:
                return result
            if result['data']:
                ac = result['data'].get('ac')
            else:
                ac = None
            user_data = await ExternalAPI.get_user_brief(bind_data.region, bind_data.uid, ac)
            if user_data['code'] != 1000:
                return user_data
            redis_key = f"bot_bind:{platform}:{user_id}"
            # 将新绑定数据写入数据库
            region_id = GameUtils.get_region_id(bind_data.region)
            result = await BotUserModel.post_user_bind(platform, user_id, region_id, bind_data.uid)
            if result['code'] != 1000:
                return result
            # 更新redis数据
            result = await RedisClient.set(redis_key, user_data['data'])
            if result['code'] != 1000:
                return result
            return user_data
        else:
            result = await ExternalAPI.get_user_search(bind_data.region, bind_data.ign, 1)
            if result['code'] != 1000:
                return result
            account_id = result['data'][0]['account_id']
            # 获取用户的基本数据
            redis_key = f"token:ac:{account_id}"
            result = await RedisClient.get(redis_key)
            if result['code'] != 1000:
                return result
            if result['data']:
                ac = result['data'].get('ac')
            else:
                ac = None
            user_data = await ExternalAPI.get_user_brief(bind_data.region, account_id, ac)
            if user_data['code'] != 1000:
                return user_data
            redis_key = f"bot_bind:{platform}:{user_id}"
            # 将新绑定数据写入数据库
            region_id = GameUtils.get_region_id(bind_data.region)
            result = await BotUserModel.post_user_bind(platform, user_id, region_id, account_id)
            if result['code'] != 1000:
                return result
            # 更新redis数据
            result = await RedisClient.set(redis_key, user_data['data'], 7*24*60*60)
            if result['code'] != 1000:
                return result
            return user_data
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def postBindByLink(platform: str, user_id: str, region: str, account_id: int):
        # 获取用户的基本数据
        redis_key = f"token:ac:{account_id}"
        result = await RedisClient.get(redis_key)
        if result['code'] != 1000:
            return result
        if result['data']:
            ac = result['data'].get('ac')
        else:
            ac = None
        user_data = await ExternalAPI.get_user_brief(region, account_id, ac)
        if user_data['code'] != 1000:
            return user_data
        redis_key = f"bot_bind:{platform}:{user_id}"
        # 将新绑定数据写入数据库
        region_id = GameUtils.get_region_id(region)
        result = await BotUserModel.post_user_bind(platform, user_id, region_id, account_id)
        if result['code'] != 1000:
            return result
        # 更新redis数据
        result = await RedisClient.set(redis_key, user_data['data'], 7*24*60*60)
        if result['code'] != 1000:
            return result
        return JSONResponse.API_1000_Success
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def activateCode(platform: str, user_id: str, code: str):
        result = await PremiumModel.use_code(platform,user_id,code)
        return result
