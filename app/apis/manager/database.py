from app.loggers import ExceptionLogger
from app.models import ShipModel


class MaintenanceAPI:
    @ExceptionLogger.handle_program_exception_async
    async def get_ship_stats():
        return await ShipModel.get_all_ship_stats()
    
    @ExceptionLogger.handle_program_exception_async
    async def refresh_ship_base(ships: dict):
        """刷新船只基础数据

        接收格式:
        {
            '123456': [is_old, tier, type_id, nation_id, rarity_id, premium, special, index_code, ship_name],
            ...
        }
        """
        return await ShipModel.refresh_ship_base(ships)