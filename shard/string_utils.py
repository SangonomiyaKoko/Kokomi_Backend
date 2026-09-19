import re
from typing import Optional


class StringUtils:

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
