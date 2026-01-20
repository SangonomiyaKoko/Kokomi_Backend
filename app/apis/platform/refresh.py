from app.network import ExternalAPI
from app.loggers import ExceptionLogger
from app.core import EnvConfig
from app.response import JSONResponse


class RefreshAPI:
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def refreshVehicles(server: str):
        result = await ExternalAPI.get_vehicles_data(server)
        return result
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def refreshConfig():
        EnvConfig.refresh_config()
        return JSONResponse.API_1000_Success