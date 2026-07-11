from app.core import EnvConfig
from app.loggers import ExceptionLogger
from app.utils import TimeUtils
from app.models import PlatformModel, ShipModel
from app.response import JSONResponse

class MaintenanceAPI:
    @ExceptionLogger.handle_program_exception_async
    async def get_database_meta():
        error, game_version = JSONResponse.extract_data(
            response=await PlatformModel.read_latest_version()
        )
        if error:
            return game_version
        
        error, table_meta = JSONResponse.extract_data(
            response=await PlatformModel.read_table_meta()
        )
        if error:
            return table_meta
        
        error, database_meta = JSONResponse.extract_data(
            response=await PlatformModel.read_database_meta()
        )
        if error:
            return database_meta
        
        error, user_activity = JSONResponse.extract_data(
            response=await PlatformModel.read_user_activity_distribution()
        )
        if error:
            return user_activity
        
        user_activity_distribution = {}
        for user in user_activity:
            user_activity_distribution[str(user[0])] = user[1]

        error, clan_activity = JSONResponse.extract_data(
            response=await PlatformModel.read_clan_activity_distribution()
        )
        if error:
            return clan_activity
        
        clan_activity_distribution = {}
        for clan in clan_activity:
            clan_activity_distribution[str(clan[0])] = clan[1]

        error_count = 0
        file = EnvConfig.LOG_DIR / f"error/{TimeUtils.now_iso()[:10]}.log"

        if file.exists():
            with open(file, "r", encoding="utf-8") as f:
                for _ in f:
                    error_count += 1

        result = {
            'version': game_version,
            'error': error_count,
            'user': {
                'total': table_meta.get('base_users', 0),
                'recent_lv1': table_meta.get('recent_lv1', 0),
                'recent_lv2': table_meta.get('recent_lv2', 0),
                'activity': user_activity_distribution
            },
            'clan': {
                'total': table_meta.get('base_clans', 0),
                'activity': clan_activity_distribution
            },
            'cache': {
                'users': table_meta.get('total_users', 0),
                'ships': table_meta.get('ship_entries', 0),
                'battles': table_meta.get('total_battles', 0),
                'rows': table_meta.get('leaderboard_rows', 0)
            },
            'mysql': {
                'tables': database_meta.get('mysql_tables', 0),
                'rows': database_meta.get('mysql_rows', 0),
                'size_kb': database_meta.get('mysql_size_kb', 0)
            },
            'sqlite': {
                'files': database_meta.get('sqlite_files', 0),
                'size_kb': database_meta.get('sqlite_size_kb', 0)
            }
        }

        return JSONResponse.success(result)
    
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