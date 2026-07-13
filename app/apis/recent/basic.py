import sqlite3
from typing import List, Dict, Any
from dataclasses import dataclass, field

from app.core import EnvConfig
from app.loggers import ExceptionLogger
from app.middlewares import RedisClient, BlacklistManager
from app.network import ExternalAPI
from app.response import JSONResponse, BasicResponse
from app.response import JSONResponse
from app.models import PlayerModel, UserStatsSyncer, RecentModel
from app.utils import TimeUtils

from .summary import RecentSummary
from .calculate import CalculateRecent
from .refresher import UserUpdater, recent_refresh_lock


@dataclass
class RecentSummaryData:
    """PVE统计数据"""
    overall: Dict[str, Any] = field(default_factory=dict)
    hot_map: List[int] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'overall': self.overall,
            'hot_map': self.hot_map
        }
    
@dataclass
class RecentStatistics:
    """Recent统计数据"""
    overall: Dict[str, Any] = field(default_factory=dict)
    battle_type: Dict[str, Any] = field(default_factory=dict)
    rows: List[Any] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'overall': self.overall,
            'battle_type': self.battle_type,
            'rows': self.rows
        }

class RecentAPI:
    @ExceptionLogger.handle_program_exception_async
    async def enable(account_id: int):
        # 从 Redis 中获取用户的 access_token
        redis_key = f"token:ac:{account_id}"
        response = await RedisClient.get_token(redis_key)
        error, access_token = JSONResponse.extract_data(response)
        if error:
            return access_token
        
        error, response = JSONResponse.extract_data(
            response=await ExternalAPI.get_user_basic(account_id, access_token)
        )
        if error:
            return response
        
        user_info = response.get(str(account_id))

        # 用户不存在(404 not found)
        if user_info is None:
            return JSONResponse.API_UserNotExist
        
        # 用户隐藏战绩
        if 'hidden_profile' in user_info:
            return JSONResponse.API_UserHiddenProfile
        
        # 用户没有战绩
        if (
            user_info is None or 
            'statistics' not in user_info or 
            'basic' not in user_info['statistics']
        ):
            return JSONResponse.API_UserDataIsNone
        
        # 刷新用户的数据库缓存数据
        error, refresh = JSONResponse.extract_data(
            response=await UserStatsSyncer.refresh(account_id, response)
        )
        if error:
            return refresh
        
        # 记录用户的调用信息
        error, record = JSONResponse.extract_data(
            response=await PlayerModel.record_query(account_id)
        )
        if error:
            return record
        
        # 先检查是否已经启用
        error, user_config = JSONResponse.extract_data(
            response=await PlayerModel.get_user_config(account_id)
        ) 
        if error:
            return user_config
        if user_config[0] == 2:
            return JSONResponse.API_1000_Success
        
        statistics = user_info['statistics']
        basic_data = statistics.get('basic', {})
        last_battle_time = basic_data.get('last_battle_time')
        current_timestamp = TimeUtils.timestamp()

        if last_battle_time and current_timestamp - last_battle_time <= 180 * 68400:
            pass
        else:
            # 返回超过 180 天未活跃策略
            return JSONResponse.API_UserNotActive
        
        return await RecentModel.set_bot_recent_level(account_id)
    
    @ExceptionLogger.handle_program_exception_async
    async def summary(account_id: int):
        # 先读数据库，读不到数据再请求
        error, user = JSONResponse.extract_data(
            response=await PlayerModel.get_user_name_and_clan(account_id)
        )
        if error:
            return user
        
        if user:
            # 记录用户的调用信息
            error, record = JSONResponse.extract_data(
                response=await PlayerModel.record_query(account_id)
            )
            if error:
                return record
        else:
            return JSONResponse.API_RecentNotEnable
        
        user_basic = user['basic']

        error, user_config = JSONResponse.extract_data(
            response=await PlayerModel.get_user_config(account_id)
        ) 
        if error:
            return user_config
        user_level = {1: "Standard",2: "Plus"}.get(user_config[0])
        storage_limit = user_config[1]
        if user_level is None:
            return JSONResponse.API_RecentNotEnable
        
        total_dates = 0
        total_rows = 0
        total_error = 0
        
        db_path = EnvConfig.SQLITE_DIR / f'{account_id}.db'
        if db_path.exists():
            file_size_kb = db_path.stat().st_size // 1024
            if file_size_kb > 1024:
                file_size_mb = '{:,}'.format(file_size_kb // 1024).replace(',', ' ')
            else:
                file_size_mb = '< 1'

            current_timestamp = TimeUtils.timestamp()

            with sqlite3.connect(db_path) as conn:
                try:
                    cursor = conn.cursor()
                    start_date = RecentSummary.read_start_date(cursor)
                    if start_date:
                        total_rows = RecentSummary.read_total_rows(cursor)
                        summary = RecentSummary.read_daily_summary(cursor, current_timestamp, start_date)
                finally:
                    cursor.close()
        
        hot_map = []
        values = list(summary.values())
        total_dates = len(values) - 1
        for i in range(total_dates):
            if values[i] is None:
                total_error += 1
                hot_map.append(None)
            elif values[i] == -1:
                hot_map.append(-1)
            else:
                if values[i+1] is None:
                    total_error += 1
                    hot_map.append(None)
                elif values[i+1] >= 0:
                    diff_battles = values[i] - values[i+1]
                    hot_map.append(max(0, diff_battles))
                else:
                    hot_map.append(0)
        
        statistics = RecentSummaryData(
            overall={
                'user_level': user_level,
                'storage_limit': str(storage_limit),
                'total_dates': str(total_dates),
                'total_rows': str(total_rows),
                'total_error': str(total_error),
                'file_size': file_size_mb
            },
            hot_map=hot_map
        )

        data = BasicResponse(
            mode='Recent',
            type='Summary',
            basic=user_basic,
            statistics=statistics.to_dict()
        )

        return JSONResponse.success(data.to_dict())

    @ExceptionLogger.handle_program_exception_async
    async def recent(account_id: int, days: int):
        # 先读数据库，读不到数据再请求
        error, user = JSONResponse.extract_data(
            response=await PlayerModel.get_user_name_and_clan(account_id)
        )
        if error:
            return user
        
        if user:
            # 记录用户的调用信息
            error, record = JSONResponse.extract_data(
                response=await PlayerModel.record_query(account_id)
            )
            if error:
                return record
        else:
            return JSONResponse.API_RecentNotEnable
        
        user_basic = user['basic']

        # 效验用户所在工会是否被拉黑
        if user_basic['clan'] and BlacklistManager.is_clan_blocked(user_basic['clan']['clan_id']):
            return JSONResponse.API_ClanInBlacklist

        error, user_config = JSONResponse.extract_data(
            response=await PlayerModel.get_user_config(account_id)
        ) 
        if error:
            return user_config
        
        # 未启用记录 Recent 数据功能
        if not (user_config and user_config[0] == 2):
            return JSONResponse.API_RecentNotEnable

        # 从 Redis 中获取用户的 access_token
        redis_key = f"token:ac:{account_id}"
        response = await RedisClient.get_token(redis_key)
        error, access_token = JSONResponse.extract_data(response)
        if error:
            return access_token
        
        current_timestamp = TimeUtils.timestamp()
        start_date = TimeUtils.get_reset_date(current_timestamp, days)
        end_date = TimeUtils.get_reset_date(current_timestamp)

        async with recent_refresh_lock(account_id) as locked:
            if not locked:
                return JSONResponse.API_AcqurieLockFailed
            
            error, responses = JSONResponse.extract_data(
                response=await ExternalAPI.get_user_recent(account_id, access_token)
            )
            if error:
                return responses

            # 效验用户当前数据是否有效
            user_info = responses[0].get(str(account_id))
            # 用户不存在(404 not found)
            if user_info is None:
                return JSONResponse.API_UserNotExist
            # 用户隐藏战绩
            if 'hidden_profile' in user_info:
                error, refresh = JSONResponse.extract_data(
                    response=await UserStatsSyncer.refresh(account_id, {str(account_id): {'hidden_profile': True}})
                )
                if error:
                    return refresh
                return JSONResponse.API_UserHiddenProfile
            # 用户没有战绩
            if (
                user_info is None or 
                'statistics' not in user_info or 
                'basic' not in user_info['statistics']
            ):
                return JSONResponse.API_UserDataIsNone
            for response in responses[1:]:
                user_info = response.get(str(account_id))
                # 用户不存在(404 not found)
                if user_info is None:
                    return JSONResponse.API_UserNotExist
                
                # 用户隐藏战绩
                if 'hidden_profile' in user_info:
                    error, refresh = JSONResponse.extract_data(
                        response=await UserStatsSyncer.refresh(account_id, {str(account_id): {'hidden_profile': True}})
                    )
                    if error:
                        return refresh
                    return JSONResponse.API_UserHiddenProfile
                
            # 刷新用户的数据库缓存数据
            error, refresh = JSONResponse.extract_data(
                response=await UserStatsSyncer.refresh(account_id, responses[0], True)
            )
            if error:
                return refresh
        
            user_info = responses[0].get(str(account_id))
            statistics = user_info['statistics']
            basic_data = statistics.get('basic', {})
            
            user_basic.update({
                'username': user_info['name'],
                'karma': basic_data.get('karma', 0),
                'insignias': user_info.get('dog_tag')
            })

            await UserUpdater.main(
                account_id=account_id,
                user_level=user_config[0],
                responses=responses,
                current_timestamp=current_timestamp,
                update_timestamp=refresh
            )
        
        result = CalculateRecent.calc_recent(account_id, start_date, end_date)

        data = BasicResponse(
            mode='Recent',
            type='Random',
            basic=user_basic,
            statistics=result
        )

        return JSONResponse.success(data.to_dict())
    

    @ExceptionLogger.handle_program_exception_async
    async def recents(account_id: int):
        # 先读数据库，读不到数据再请求
        error, user = JSONResponse.extract_data(
            response=await PlayerModel.get_user_name_and_clan(account_id)
        )
        if error:
            return user
        
        if user:
            # 记录用户的调用信息
            error, record = JSONResponse.extract_data(
                response=await PlayerModel.record_query(account_id)
            )
            if error:
                return record
        else:
            return JSONResponse.API_RecentNotEnable
        
        user_basic = user['basic']

        # 效验用户所在工会是否被拉黑
        if user_basic['clan'] and BlacklistManager.is_clan_blocked(user_basic['clan']['clan_id']):
            return JSONResponse.API_ClanInBlacklist

        error, user_config = JSONResponse.extract_data(
            response=await PlayerModel.get_user_config(account_id)
        ) 
        if error:
            return user_config
        
        # 未启用记录 Recent 数据功能
        if not (user_config and user_config[0] == 2):
            return JSONResponse.API_RecentNotEnable

        # 从 Redis 中获取用户的 access_token
        redis_key = f"token:ac:{account_id}"
        response = await RedisClient.get_token(redis_key)
        error, access_token = JSONResponse.extract_data(response)
        if error:
            return access_token
        
        current_timestamp = TimeUtils.timestamp()

        async with recent_refresh_lock(account_id) as locked:
            if not locked:
                return JSONResponse.API_AcqurieLockFailed
            
            error, responses = JSONResponse.extract_data(
                response=await ExternalAPI.get_user_recent(account_id, access_token)
            )
            if error:
                return responses

            # 效验用户当前数据是否有效
            user_info = responses[0].get(str(account_id))
            # 用户不存在(404 not found)
            if user_info is None:
                return JSONResponse.API_UserNotExist
            # 用户隐藏战绩
            if 'hidden_profile' in user_info:
                error, refresh = JSONResponse.extract_data(
                    response=await UserStatsSyncer.refresh(account_id, {str(account_id): {'hidden_profile': True}})
                )
                if error:
                    return refresh
                return JSONResponse.API_UserHiddenProfile
            # 用户没有战绩
            if (
                user_info is None or 
                'statistics' not in user_info or 
                'basic' not in user_info['statistics']
            ):
                return JSONResponse.API_UserDataIsNone
            for response in responses[1:]:
                user_info = response.get(str(account_id))
                # 用户不存在(404 not found)
                if user_info is None:
                    return JSONResponse.API_UserNotExist
                
                # 用户隐藏战绩
                if 'hidden_profile' in user_info:
                    error, refresh = JSONResponse.extract_data(
                        response=await UserStatsSyncer.refresh(account_id, {str(account_id): {'hidden_profile': True}})
                    )
                    if error:
                        return refresh
                    return JSONResponse.API_UserHiddenProfile
                
            # 刷新用户的数据库缓存数据
            error, refresh = JSONResponse.extract_data(
                response=await UserStatsSyncer.refresh(account_id, responses[0], True)
            )
            if error:
                return refresh
        
            user_info = responses[0].get(str(account_id))
            statistics = user_info['statistics']
            basic_data = statistics.get('basic', {})
            
            user_basic.update({
                'username': user_info['name'],
                'karma': basic_data.get('karma', 0),
                'insignias': user_info.get('dog_tag')
            })

            await UserUpdater.main(
                account_id=account_id,
                user_level=user_config[0],
                responses=responses,
                current_timestamp=current_timestamp,
                update_timestamp=refresh
            )
        
        result = CalculateRecent.get_recents(account_id)

        data = BasicResponse(
            mode='Recent',
            type='Plus',
            basic=user_basic,
            statistics=result
        )

        return JSONResponse.success(data.to_dict())