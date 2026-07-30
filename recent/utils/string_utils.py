import json

class StringUtils:
    def ship_snapshot_encode(data: list):
        parts = []
        for item in data:
            if item is None:
                parts.append('')
            else:
                parts.append(str(item).replace(' ', ''))
        return ';'.join(parts)

    def ship_snapshot_decode(data: str):
        fields = data.split(';')
        result = []
        for f in fields:
            if f == '':
                result.append(None)
            else:
                result.append(eval(f))
        return result

    def ship_map_encode(data: dict):
        parts = []
        for key, value in data.items():
            parts.append(str(key) + ':' + str(value))
        return ','.join(parts)