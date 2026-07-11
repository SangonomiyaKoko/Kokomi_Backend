import csv
from typing import Dict, List, Union

from app.core import EnvConfig
from app.constants import GameData


class DevUtils:
    """特殊开发模式下，部分数据通过读取本地缓存数据而非加载数据库中的最新数据"""
    
    @staticmethod
    def read_ship_stats() -> Dict[str, List[float]]:
        """从本地 CSV 文件读取船只统计数据"""
        file_path = EnvConfig.INIT_DIR / "data/ship_stats.csv"
        if not file_path.exists():
            return {}
        
        result = {}
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)  # 列名: ship_id, win_rate, avg_damage, avg_frags
            for row in reader:
                ship_id = str(row['ship_id'])
                win_rate = float(row['win_rate'])
                avg_damage = float(row['avg_damage'])
                avg_frags = float(row['avg_frags'])
                result[ship_id] = [win_rate, avg_damage, avg_frags]
        return result
    
    @staticmethod
    def read_ship_info() -> Dict[str, List[Union[int, str]]]:
        """从本地 CSV 文件读取船只基本信息"""
        if EnvConfig.REGION == 'ru':
            file_path = EnvConfig.INIT_DIR / "data/ship_name_lesta.csv"
        else:
            file_path = EnvConfig.INIT_DIR / "data/ship_name_wg.csv"

        if not file_path.exists():
            return {}
        
        result = {}
        with open(file_path, mode='r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            for row in reader:
                ship_id = str(row['ship_id'])
                is_old = int(row['is_old'])
                tier = int(row['tier'])
                type_id = row['type_id']
                nation_id = row['nation_id']
                result[ship_id] = [
                    is_old, 
                    tier, 
                    GameData.SHIP_TYPE_MAP.get(type_id, 'Destroyer'), 
                    GameData.SHIP_NATION_MAP.get(nation_id, 'usa')
                ]
        return result