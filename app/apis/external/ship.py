from app.loggers import ExceptionLogger
from app.models import ShipModel
from app.response import JSONResponse

class ShipStatsExternalAPI:
    @ExceptionLogger.handle_program_exception_async
    async def get_ship_stats():
        error, ship_stats = JSONResponse.extract_data(
            response=await ShipModel.get_all_ship_stats()
        )
        if error: 
            return ship_stats
        
        result = []
        for ship_id, ship_data in ship_stats.items():
            result.append({
                'ship_id': ship_id,
                'battles': ship_data[0],
                'win_rate': ship_data[1],
                'avg_damage': ship_data[2],
                'avg_frags': ship_data[3],
                'avg_exp': ship_data[4]
            })
        
        return JSONResponse.success(result)