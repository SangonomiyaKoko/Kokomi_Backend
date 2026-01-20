from app.models import GameModel
from app.network import ExternalAPI
from app.loggers import ExceptionLogger
from app.response import JSONResponse

class UpdateAPI:
    @staticmethod
    @ExceptionLogger.handle_program_exception_async
    async def updateGameVersion(region: str):
        result = await ExternalAPI.get_game_version(region)
        if result['code'] == 1000:
            update_result = await GameModel.update_game_version(region, result['data'])
            if update_result['code'] == 1000:
                return JSONResponse.get_success_response({'region': region, 'version': result['data']})
            else:
                return update_result
        else:
            return result