from app.core import EnvConfig
from app.loggers import ExceptionLogger
from app.middlewares import RedisClient, BlacklistManager
from app.response import JSONResponse, ResponseDict
from app.models import DemoPlayerModel, PlayerModel, ShipModel

class BlacklistManagerAPI:
    @ExceptionLogger.handle_program_exception_async
    async def block_user(account_id: int) -> ResponseDict:
        BlacklistManager.add_user(account_id)

        return JSONResponse.API_1000_Success
            
    @ExceptionLogger.handle_program_exception_async
    async def block_clan(clan_id: int) -> ResponseDict:
        BlacklistManager.add_clan(clan_id)
            
        return JSONResponse.API_1000_Success

    @ExceptionLogger.handle_program_exception_async
    async def clear_user(account_id: int) -> ResponseDict:
        """完全清理用户数据
        
        1. 清理用户可能存在的排行榜 redis key
        2. 清理用户在数据库中的排行榜缓存
        3. 清理用户在数据库所有表中的数据
        """
        error, ship_ids = JSONResponse.extract_data(
            response=await ShipModel.get_ranking_ship_ids()
        )
        if error:
            return ship_ids
        
        # 读取用户已缓存的数据
        error, user_cache = JSONResponse.extract_data(
            response=await PlayerModel.get_user_cache(account_id)
        )
        if error:
            return user_cache
        
        delete_ids = []
        for ship_id, ship_data in user_cache.items():
            if int(ship_id) not in ship_ids:
                continue
            min_battles = ship_ids.get(int(ship_id))
            if ship_data[0] >= min_battles:
                delete_ids.append(ship_id)

        if len(delete_ids) > 0:
            # 先删除redis缓存
            error, deleted = JSONResponse.extract_data(
                response=await RedisClient.zrem_member(
                    [f'leaderboard:ship:{sid}' for sid in delete_ids], 
                    str(account_id)
                )
            )
            if error:
                return deleted
            
            # 再删除mysql数据
            error, deleted = JSONResponse.extract_data(
                response=await DemoPlayerModel.remove_user_ranking(account_id, delete_ids)
            )
            if error:
                return deleted
            
        # 清除用户在数据库中的数据
        error, clear = JSONResponse.extract_data(
            response=await PlayerModel.del_user_data(account_id)
        )
        if error:
            return clear
        
        # 清除可能存在的用户Recent数据库文件
        db_path = EnvConfig.SQLITE_DIR / f'{account_id}.db'
        db_path.unlink(True)

        return JSONResponse.API_1000_Success