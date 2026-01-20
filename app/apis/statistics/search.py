from app.network import ExternalAPI
from app.utils import NameUtils
from app.response import JSONResponse
from app.loggers import ExceptionLogger
from app.schemas import ShipFilter


class SearchAPI:
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def search_user(
        region: str,
        content: str,
        limit: int
    ):
        result = await ExternalAPI.get_user_search(region, content, limit)
        return result
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def search_clan(
        region: str,
        content: str,
        limit: int
    ):
        result = await ExternalAPI.get_clan_search(region, content, limit)
        return result
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def search_ship(
        region: str,
        content: str,
        language: str
    ):
        result = JSONResponse.get_success_response(NameUtils.search_ship(region,content,language))
        return result
    
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def query_ship(
        region: str,
        query_condition: ShipFilter
    ):
        result = NameUtils.query_ship(region, query_condition)
        if result == {}:
            return JSONResponse.API_2006_ShipDataNotMatched
        elif len(result) >= 50:
            return JSONResponse.API_2005_QueryConditionsTooBroad
        else:
            return JSONResponse.get_success_response(result)