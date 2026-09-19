from typing import Optional, TypedDict

from .string_utils import StringUtils


# 定义战斗统计数据的 TypedDict
class BattleStatsDict(TypedDict):
    battles: int
    total_exp: int
    win_rate: float
    avg_damage: int
    avg_frags: float
    avg_exp: int
    max_exp: int
    max_frags: int
    max_planes: int
    max_damage: int
    max_scouting: int
    max_potential: int


# 定义用户基础数据的 TypedDict
class UserBasicDataDict(TypedDict):
    username: str
    is_enabled: int
    is_public: int
    total_battles: int
    pve_battles: int
    pvp_battles: int
    ranked_battles: int
    rating_battles: int
    register_time: Optional[int]
    last_battle_at: Optional[int]
    karma: int
    insignias: Optional[str]
    random_stats: Optional[BattleStatsDict]
    ranked_stats: Optional[BattleStatsDict]


class ParseUtils:
    """数据解析相关公用函数"""

    @staticmethod
    def user_basic_data(
        region: str, 
        account_id: int, 
        response: dict
    ) -> UserBasicDataDict:
        """从 API 响应中提取用户基础数据
        
        返回以下形式的数据：
        - 用户不存在，无有效字段且 is_enabled = 0
        - 用户隐藏战绩，仅 name 字段有效且 is_public = 0
        - 用户无数据，仅 name 和 registe 字段有效
        - 用户有数据，所有字段均有效
        """
        user_data: UserBasicDataDict = {
            'username': None,
            'is_enabled': 1,
            'is_public': 1,
            'total_battles': 0,
            'pve_battles': 0,
            'pvp_battles': 0,
            'ranked_battles': 0,
            'rating_battles': 0,
            'register_time': None,
            'last_battle_at': None,
            'karma': 0,
            'insignias': None,
            'random_stats': None,
            'ranked_stats': None
        }
        
        user_info = response.get(str(account_id))
        
        # 无有效数据
        if user_info is None:
            user_data['is_enabled'] = 0
            return user_data

        # 隐藏战绩
        if 'hidden_profile' in user_info:
            user_data['is_public'] = 0
            user_data['username'] = user_info['name']
            return user_data
        
        # 无有效数据
        if 'statistics' not in user_info:
            user_data['is_enabled'] = 0
            return user_data

        # 用户名称和注册时间戳
        # 这两个关键字段缺失应当判定为接口返回值异常直接抛出
        user_data['username'] = user_info['name']
        user_data['register_time'] = int(user_info['created_at'])
        if user_data['register_time'] == 0:
            user_data['is_enabled'] = 0
            user_data['register_time'] = None
            return user_data
        
        # 无数据账号
        if 'basic' not in user_info['statistics']:
            return user_data
        
        # 正常有数据用户
        statistics = user_info['statistics']
        basic_data = statistics.get('basic', {})
        leveling_points = basic_data.get('leveling_points', 0)
        
        # 处理中国服主播体验账号的特殊等级点数偏移量（1,000,000）
        if leveling_points >= 1_000_000:
            leveling_points -= 1_000_000
        
        # 最后战斗时间戳
        last_battle_time = basic_data.get('last_battle_time', 0)
        if last_battle_time == 0:
            last_battle_time = None

        pve_battles = statistics.get('pve', {}).get('battles_count', 0)
        pvp_battles = statistics.get('pvp', {}).get('battles_count', 0)
        ranked_battles = statistics.get('rank_solo', {}).get('battles_count', 0)
        encoded_insignias = StringUtils.insignias_encode(user_info.get('dog_tag'))
        
        user_data.update({
            'username': user_info['name'],
            'total_battles': leveling_points,
            'pve_battles': pve_battles,
            'pvp_battles': pvp_battles,
            'ranked_battles': ranked_battles,
            'last_battle_at': last_battle_time,
            'karma': basic_data.get('karma', 0),
            'insignias': encoded_insignias
        })
        
        # 处理俄服的评分战数据
        if region == 'ru':
            rating_count = 0
            rating_count += statistics.get('rating_solo', {}).get('battles_count', 0)
            rating_count += statistics.get('rating_div', {}).get('battles_count', 0)
            user_data['rating_battles'] = rating_count

        if pvp_battles > 0:
            user_data['random_stats'] = {
                'battles': pvp_battles,
                'total_exp': statistics['pvp']['exp'],
                'win_rate': round(statistics['pvp']['wins']/pvp_battles*100, 2),
                'avg_damage': int(statistics['pvp']['damage_dealt']/pvp_battles),
                'avg_frags': round(statistics['pvp']['frags']/pvp_battles, 2),
                'avg_exp': int(statistics['pvp']['original_exp']/pvp_battles),
                'max_exp': statistics['pvp']['max_exp'],
                'max_frags': statistics['pvp']['max_frags'],
                'max_planes': statistics['pvp']['max_planes_killed'],
                'max_damage': statistics['pvp']['max_damage_dealt'],
                'max_scouting': statistics['pvp']['max_scouting_damage'],
                'max_potential': statistics['pvp']['max_total_agro']
            }
        
        if ranked_battles > 0:
            user_data['ranked_stats'] = {
                'battles': ranked_battles ,
                'total_exp': statistics['rank_solo']['exp'],
                'win_rate': round(statistics['rank_solo']['wins']/ranked_battles*100, 2),
                'avg_damage': int(statistics['rank_solo']['damage_dealt']/ranked_battles),
                'avg_frags': round(statistics['rank_solo']['frags']/ranked_battles, 2),
                'avg_exp': int(statistics['rank_solo']['original_exp']/ranked_battles),
                'max_exp': statistics['rank_solo']['max_exp'],
                'max_frags': statistics['rank_solo']['max_frags'],
                'max_planes': statistics['rank_solo']['max_planes_killed'],
                'max_damage': statistics['rank_solo']['max_damage_dealt'],
                'max_scouting': statistics['rank_solo']['max_scouting_damage'],
                'max_potential': statistics['rank_solo']['max_total_agro']
            }
        
        return user_data