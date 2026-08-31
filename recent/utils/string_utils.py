from typing import Optional

class StringUtils:
    @staticmethod
    def stats_encode(data: list) -> Optional[str]:
        """将统计字段列表序列化为逗号分隔字符串，用于 ship_index_data 的 data_type_N 列"""
        if not data:
            return None
        return ','.join(map(str, data))

    @staticmethod
    def stats_decode(data: str) -> list[int]:
        """反序列化逗号分隔字符串为整数列表"""
        if not data:
            return []
        return [int(x) for x in data.split(',')]

    @staticmethod
    def index_map_encode(data: dict) -> Optional[str]:
        """将船只索引合集序列化为 `ship_id:index,...` 字符串，用于 ship_index_map 的 index_map 列"""
        if not data:
            return None
        return ','.join(f'{key}:{value}' for key, value in data.items())

    @staticmethod
    def index_map_decode(data: str) -> dict:
        """反序列化 `ship_id:index,...` 字符串为字典，键为 int，值为 int"""
        result = {}
        if not data:
            return result
        for part in data.split(','):
            key, value = part.split(':')
            result[int(key)] = int(value)
        return result
