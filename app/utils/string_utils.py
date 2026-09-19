import json
import hashlib


class StringUtils:
    """API 侧专用的字符串处理工具

    DogTag 标识串的编解码等通用能力由 shard.StringUtils 提供，
    此处仅保留 API 侧独有的实现。
    """

    @staticmethod
    def generate_ship_hash(data_dict: dict) -> str:
        json_str = json.dumps(
            data_dict,
            ensure_ascii=True,
            separators=(',', ':')
        )
        hash_obj = hashlib.sha256(json_str.encode('utf-8'))
        return hash_obj.hexdigest()
