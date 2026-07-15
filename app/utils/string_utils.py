
import json
import hashlib
from typing import Optional, Dict

class StringUtils:
    """字符串解析相关工具函数集合"""
    
    @staticmethod
    def serialize_insignias(data: Dict[str, int]) -> Optional[str]:
        """将 DogTag 数据字典序列化为标识字符串"""
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
        
        return "-".join(str(data[k]) for k in keys)
    
    @staticmethod
    def parse_insignias(insignia_str: str | None) -> Optional[Dict[str, int]]:
        """将标识字符串解析为 DogTag 数据字典"""
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
        
        return {key: int(part) for key, part in zip(keys, parts)}
    
    @staticmethod
    def generate_ship_hash(data_dict: dict) -> str:
        json_str = json.dumps(
            data_dict,
            ensure_ascii=True,
            separators=(',', ':')
        )
        with open('temp.json', "w", encoding="utf-8") as f:
            json.dump(data_dict,f,ensure_ascii=True,separators=(',', ':'))
        hash_obj = hashlib.sha256(json_str.encode('utf-8'))
        return hash_obj.hexdigest()