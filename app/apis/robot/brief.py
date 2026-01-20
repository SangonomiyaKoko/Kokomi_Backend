# from app.loggers import ExceptionLogger
# from app.network import ExternalAPI
# from app.middlewares import RedisClient


# class BriefAPI:
#     @staticmethod
#     @ExceptionLogger.handle_program_exception_async
#     async def getBriefByIGN(region: str, ign: str):
#         # 从接口获取用户名称搜索数据
#         result = await ExternalAPI.get_user_search(region, ign, 1)
#         if result['code'] != 1000:
#             return result
#         account_id = result['data'][0]['account_id']
#         # 获取用户的基本数据
#         redis_key = f"token:ac:{account_id}"
#         result = await RedisClient.get(redis_key)
#         if result['code'] != 1000:
#             return result
#         if result['data']:
#             ac = result['data'].get('ac')
#         else:
#             ac = None
#         return await ExternalAPI.get_user_brief(region, account_id, ac)
    
#     @staticmethod
#     @ExceptionLogger.handle_program_exception_async
#     async def getBriefByUID(region: str, account_id: int):
#         # 获取用户的基本数据
        
#         redis_key = f"token:ac:{account_id}"
#         result = await RedisClient.get(redis_key)
#         if result['code'] != 1000:
#             return result
#         if result['data']:
#             ac = result['data'].get('ac')
#         else:
#             ac = None
#         return await ExternalAPI.get_user_brief(region, account_id, ac)
