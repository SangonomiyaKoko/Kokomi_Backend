from app.core import EnvConfig, AppState
from app.loggers import ExceptionLogger
from app.response import JSONResponse
from app.models import ShipModel
from app.utils import StringUtils
from app.middlewares import RedisClient

class StateAPI:
    @ExceptionLogger.handle_program_exception_async
    async def get_node_state():
        result = {
            "region": EnvConfig.REGION,
            "available": False,
            'name_hash': None,
            "services": {}
        }
        error, hash_data = JSONResponse.extract_data(
            response=await ShipModel.get_ship_data_for_hash()
        )
        if error:
            return hash_data
        
        result['name_hash'] = StringUtils.generate_ship_hash(hash_data)
        
        constant = EnvConfig.get_constants()
        services = constant.SERVICE_LIST
        if EnvConfig.DEV_MODE or not AppState.is_available():
            for service in services:
                result['services'][service] = 0
        else:
            result['available'] = True
            for service in services:
                key = f'status:{service}'
                error, data = JSONResponse.extract_data(
                    response=await RedisClient.exists(key)
                )
                if error:
                    result['services'][service] = 0
                elif data:
                    result['services'][service] = 1
                else:
                    result['services'][service] = 0

        return JSONResponse.success(result)
    
    @ExceptionLogger.handle_program_exception_async
    async def set_node_state(available: bool):
        """修改节点的全局状态"""
        key = 'status:maintenance'

        if available:
            error, response = JSONResponse.extract_data(
                response=await RedisClient.drop(key)
            )
        else:
            error, response = JSONResponse.extract_data(
                response=await RedisClient.set(key, 1)
            )
        if error:
            return response
        
        AppState.set_available(available)

        result = {
            "available": AppState.is_available()
        }
        return JSONResponse.success(result)