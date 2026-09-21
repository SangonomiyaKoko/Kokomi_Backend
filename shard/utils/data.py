import json
import re
from pathlib import Path
from typing import Optional, TypedDict
from json import JSONDecodeError


class StringUtils:
    """字符串编解码相关公用函数"""

    @staticmethod
    def is_date_format(value: str) -> bool:
        """简单效验传入的字符串是否符合日期格式"""
        return bool(
            re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
        )

    @staticmethod
    def token_decode(data: str) -> list:
        """解析读取得到 AC 字段中数据"""
        # 数据格式： TOKEN or TOKEN:ID1,ID2,...
        if data is None:
            return [None, None]

        if ':' not in data:
            # 未配置绑定账号
            return [data, None]

        split_str = data.split(':')
        token = split_str[0]
        users = split_str[1]

        # 根据参数数量分割字符串
        if users is None:
            return [token, None]
        elif ',' not in users:
            return [token, [users]]
        else:
            return [token, users.split(',')]

    @staticmethod
    def insignias_encode(data: dict) -> Optional[str]:
        """从 DogTag 数据中生成标识字符串"""
        if not data:
            return None

        keys = [
            "texture_id",
            "symbol_id",
            "border_color_id",
            "background_color_id",
            "background_id"
        ]

        if any(k not in data for k in keys):
            return None

        return "-".join(
            str(data[k]) for k in keys
        )

    @staticmethod
    def insignias_decode(insignia_str: str) -> Optional[dict]:
        """将储存的 DogTag 字符串反序列化为 Dict"""
        if insignia_str is None:
            return None

        parts = insignia_str.split("-")

        keys = [
            "texture_id",
            "symbol_id",
            "border_color_id",
            "background_color_id",
            "background_id"
        ]

        if len(parts) != len(keys):
            return None

        return {
            key: int(part) for key, part in zip(keys, parts)
        }

    @staticmethod
    def index_data_encode(data: list) -> Optional[str]:
        """将统计字段列表序列化为用于储存的 index_data 字符串"""
        if not data:
            return None

        return ','.join(
            map(str, data)
        )

    @staticmethod
    def index_data_decode(data: str) -> list[int]:
        """将储存的 index_data 数据反序列化为用于计算的 List"""
        if not data:
            return []

        return [
            int(x) for x in data.split(',')
        ]

    @staticmethod
    def index_map_encode(data: dict) -> Optional[str]:
        """将船只索引合集序列化为用于储存的 index_map 字符串"""
        if not data:
            return None

        return ','.join(
            f'{key}:{value}' for key, value in data.items()
        )

    @staticmethod
    def index_map_decode(data: str) -> dict:
        """将储存的 index_map 数据反序列化为用于计算的 Dict"""
        result = {}
        if not data:
            return result

        for part in data.split(','):
            key, value = part.split(':')
            result[int(key)] = int(value)

        return result


class FileUtils:
    """文件装载相关公用函数"""

    @staticmethod
    def load_json(
        fp: Path, default: Optional[dict] = None
    ) -> dict:
        """加载 JSON 文件，未配置 default 则默认为必要文件
        
        如果必要文件不存在、读取失败或解析失败将抛出异常
        """
        if default is None:
            if not fp.exists():
                raise FileNotFoundError(f'File missing: {fp}')
            
            with open(fp, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            if not fp.exists():
                return default
            
            with open(fp, "r", encoding="utf-8") as f:
                try:
                    return json.load(f)
                except JSONDecodeError:
                    return default
        

    @staticmethod
    def load_sql(
        fp: Path
    ) -> Optional[str]:
        """加载数据库初始化 SQL 文件"""
        if not fp.exists():
            raise FileNotFoundError(f'File missing: {fp}')

        with open(fp, "r", encoding="utf-8") as f:
            return f.read()


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
