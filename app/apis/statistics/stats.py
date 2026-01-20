from app.response import JSONResponse
from app.loggers import ExceptionLogger
from app.models import PlatyerModel
from app.utils import GameUtils, JsonUtils
from app.middlewares import RedisClient
from app.network import ExternalAPI
from .processing import (
    pvp_calculate_rating, 
    processing_overall_data, 
    processing_battle_type_data,
    processing_ship_type_data,
    processing_pvp_chart
)

class StatsAPI:
    @ExceptionLogger.handle_program_exception_async
    async def refresh_user_cache(region: str, account_id: int):
        redis_key = f"token:ac:{account_id}"
        result = await RedisClient.get(redis_key)
        if result['code'] != 1000:
            return result
        if result['data']:
            ac = result['data'].get('ac')
        else:
            ac = None
        result = await ExternalAPI.get_user_basic(region, account_id, ac)
        return result
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def get_user_pvp(
        region: str,
        account_id: int,
        field: str = None
    ):
        region_id = GameUtils.get_region_id(region)
        redis_key = f"token:ac:{account_id}"
        result = await RedisClient.get(redis_key)
        if result['code'] != 1000:
            return result
        if result['data']:
            ac = result['data'].get('ac')
        else:
            ac = None
        # 先读数据库，读不到数据再请求
        result = await PlatyerModel.get_user_brief(region_id, account_id)
        if result['code'] != 1000:
            return result
        if result['data'] is None:
            # 数据库中无用户数据，进行网络请求获取数据
            result = await ExternalAPI.get_user_brief(region, account_id, ac)
            if result['code'] != 1000:
                return result
        data = {
            'type': field,
            'basic': result['data'],
            'statistics': {}
        }
        result = await ExternalAPI.get_user_pvp(region, account_id, ac, field)
        if result['code'] != 1000:
            return result
        data['statistics'] = {
            'overall': {},
            'battle_type': {},
            'ship_type': {},
            'record': {},
            'chart': {}
        }
        
        server_data = JsonUtils.read('ship_data')
        if region == 'ru':
            shipid_data = JsonUtils.read('ship_name_lesta')
        else:
            shipid_data = JsonUtils.read('ship_name_wg')
        original_data = pvp_calculate_rating(region, result['data']['original_data'], server_data['ship_data'])
        data['statistics']['overall'] = processing_overall_data(original_data, 'pvp')
        data['statistics']['battle_type'] = processing_battle_type_data(original_data)
        data['statistics']['ship_type'] = processing_ship_type_data(original_data, 'pvp', shipid_data)
        data['statistics']['chart'] = processing_pvp_chart(original_data, shipid_data)
        data['statistics']['record'] = result['data']['record']

        return JSONResponse.get_success_response(data)