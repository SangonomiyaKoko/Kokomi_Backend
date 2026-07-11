from typing import List, Dict, Any
from dataclasses import dataclass, field

from app.core import EnvConfig
from app.utils import DevUtils
from app.response import JSONResponse, BasicResponse
from app.loggers import ExceptionLogger
from app.network import ExternalAPI
from app.middlewares import RedisClient, BlacklistManager
from app.models import PlayerModel, ShipModel, UserStatsSyncer

from .basic import BasicAPI
from .process import format_overall, accumulate_overall
from .schema import OriginalData, ProcessedData


@dataclass
class PVEStatistics:
    """PVE统计数据"""
    overall: Dict[str, Any] = field(default_factory=dict)
    ship_type: Dict[str, Any] = field(default_factory=dict)
    record: Dict[str, Any] = field(default_factory=dict)
    chart: List[List[int]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'overall': self.overall,
            'ship_type': self.ship_type,
            'record': self.record,
            'chart': self.chart
        }

class PVEAPI:
    @ExceptionLogger.handle_program_exception_async
    async def overall(
        account_id: int, 
        include_old: bool = False
    ):
        if EnvConfig.DEV_MODE:
            # 跳过读取数据库步骤，后续直接请求 API 获取数据
            access_token = None
            user = None
        else:
            # 从 Redis 中获取用户的 access_token
            redis_key = f"token:ac:{account_id}"
            response = await RedisClient.get_token(redis_key)
            error, access_token = JSONResponse.extract_data(response)
            if error:
                return access_token
            
            # 先读数据库，读不到数据再请求
            error, user = JSONResponse.extract_data(
                response=await PlayerModel.get_user_name_and_clan(account_id)
            )
            if error:
                return user
            
            # 记录用户的调用信息
            if user:
                error, record = JSONResponse.extract_data(
                    response=await PlayerModel.record_query(account_id)
                )
                if error:
                    return record
            
        # 用户不存在
        if user and user['stats'] is None:
            return JSONResponse.API_UserNotExist
        
        # 通过 API 接口读取用户的基本信息：
        # 1. 没有读取到用户的缓存数据
        # 2. 用户的缓存数据表示该用户可能隐藏战绩
        if user is None or user['stats'] != True:
            error, user_basic = JSONResponse.extract_data(
                response=await BasicAPI.get_user_basic(account_id, access_token)
            )
            if error:
                return user_basic
        else:
            # 从数据库中读取到的用户缓存数据
            user_basic = user['basic']

        # 效验用户所在工会是否被拉黑
        if user_basic['clan'] and BlacklistManager.is_clan_blocked(user_basic['clan']['clan_id']):
            return JSONResponse.API_ClanInBlacklist
    
        error, response = JSONResponse.extract_data(
            response=await ExternalAPI.get_user_pve(account_id, access_token)
        )
        if error:
            return response
        
        if 'hidden_profile' in response.get(str(account_id)):
            if not EnvConfig.DEV_MODE:
                error, refresh = JSONResponse.extract_data(
                    response=await UserStatsSyncer.refresh(account_id, {str(account_id): {'hidden_profile': True}})
                )
                if error:
                    return refresh
            return JSONResponse.API_UserHiddenProfile
    
        if EnvConfig.DEV_MODE:
            ship_info = DevUtils.read_ship_info()
        else:
            error, ship_info = JSONResponse.extract_data(
                response=await ShipModel.get_ship_base()
            )
            if error:
                return ship_info
            
        old_ship_ids = []
        for ship_id, ship_base in ship_info.items():
            if ship_base[0]:
                old_ship_ids.append(ship_id)

        # 将 API 数据进行初步筛选、处理、计算
        original_data = {}
        record = {
            'max_damage_dealt': 0,
            'max_frags': 0,
            'max_exp': 0,
            'max_planes_killed': 0,
            'max_scouting_damage': 0,
            'max_total_agro': 0
        }
        response = response.get(str(account_id)).get('statistics', {})

        for ship_id, ship_data in response.items():
            if not include_old and ship_id in old_ship_ids:
                continue

            field_data = ship_data.get('pve', {})
            if field_data == {}:
                continue

            if ship_id not in original_data:
                original_data[ship_id] = OriginalData.copy()

            for key in ['battles_count','wins','damage_dealt','frags','original_exp']:
                original_data[ship_id][key] += field_data[key]

            for key in ['max_damage_dealt','max_frags','max_exp','max_planes_killed','max_scouting_damage','max_total_agro']:
                if field_data[key] > record[key]:
                    record[key] = field_data[key]
        
        if original_data == {}:
            return JSONResponse.API_NoStatisticsData

        ShipTypeIndex = {
            'AirCarrier': 0,
            'Battleship': 1,
            'Cruiser': 2,
            'Destroyer': 3,
            'Submarine': 4
        }
        original_chart_data = [[0,0,0,0,0] for _ in range(11)]
        original_overall_data = ProcessedData.copy()
        original_ship_type_data = {
            'AirCarrier': ProcessedData.copy(),
            'Battleship': ProcessedData.copy(),
            'Cruiser': ProcessedData.copy(),
            'Destroyer': ProcessedData.copy(),
            'Submarine': ProcessedData.copy()
        }

        for ship_id, ship_data in original_data.items():
            ship_base = ship_info.get(ship_id)
            if ship_base is None:
                continue
            ship_tier = ship_base[1]
            ship_type = ship_base[2]
            
            accumulate_overall(original_overall_data, ship_data)
            accumulate_overall(original_ship_type_data[ship_type], ship_data)
            original_chart_data[ship_tier-1][ShipTypeIndex[ship_type]] += ship_data['battles_count']

        statistics = PVEStatistics(
            overall=format_overall(original_overall_data),
            ship_type={
                'AirCarrier': format_overall(original_ship_type_data['AirCarrier']),
                'Battleship': format_overall(original_ship_type_data['Battleship']),
                'Cruiser': format_overall(original_ship_type_data['Cruiser']),
                'Destroyer': format_overall(original_ship_type_data['Destroyer']),
                'Submarine': format_overall(original_ship_type_data['Submarine'])
            },
            record={
                'damage': '{:,}'.format(record['max_damage_dealt']).replace(',', ' '),
                'exp': '{:,}'.format(record['max_exp']).replace(',', ' '),
                'frags': '{:,}'.format(record['max_frags']).replace(',', ' '),
                'planes': '{:,}'.format(record['max_planes_killed']).replace(',', ' '),
                'scout': '{:,}'.format(record['max_scouting_damage']).replace(',', ' '),
                'potent': '{:,}'.format(record['max_total_agro']).replace(',', ' ')
            },
            chart=original_chart_data
        )

        data = BasicResponse(
            mode='PvE',
            type='Overall',
            basic=user_basic,
            statistics=statistics.to_dict()
        )

        return JSONResponse.success(data.to_dict())
    