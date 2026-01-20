from app.constants import GameData
from app.schemas import ShipFilter
from .json_utils import JsonUtils


def name_format(in_str: str) -> str:
    in_str_list = in_str.split()
    in_str = None
    in_str = ''.join(in_str_list)
    en_list = {
        'a': ['à', 'á', 'â', 'ã', 'ä', 'å'],
        'e': ['è', 'é', 'ê', 'ë'],
        'i': ['ì', 'í', 'î', 'ï'],
        'o': ['ó', 'ö', 'ô', 'õ', 'ò', 'ō'],
        'u': ['ü', 'û', 'ú', 'ù', 'ū'],
        'y': ['ÿ', 'ý'],
        'l': ['ł']
    }
    for en, lar in en_list.items():
        for index in lar:
            if index in in_str:
                in_str = in_str.replace(index, en)
            if index.upper() in in_str:
                in_str = in_str.replace(index.upper(), en.upper())
    re_str = ['_', '-', '·', '.', '\'','(',')','（','）']
    for index in re_str:
        if index in in_str:
            in_str = in_str.replace(index, '')
    in_str = in_str.lower()
    return in_str

def data_format(ship_id: int, main_data: dict):
    return {
        "id": ship_id,
        "tier": main_data[ship_id]['tier'], 
        "type": main_data[ship_id]['type'], 
        "nation": main_data[ship_id]['nation'], 
        "premium": main_data[ship_id]['premium'], 
        "special": main_data[ship_id]['special'], 
        "index": main_data[ship_id]['index'], 
        "ship_name": {
            'cn': main_data[ship_id]['ship_name']['cn'],
            'en': main_data[ship_id]['ship_name']['en'],
            'ja': main_data[ship_id]['ship_name']['ja'],
            'ru': main_data[ship_id]['ship_name']['ru'],
            "en_full": main_data[ship_id]['ship_name']['en_l'],
        }
    }

class NameUtils:    
    @staticmethod
    def search_ship(region: str, ship_name: str, language: str):
        '''
        搜索用户输出的名称对应的船只。按照先精确匹配，无果再模糊匹配的原则。

        参数:
            region: 服务器
            ship_name: 搜索的名称
            language: 搜索的语言
        '''
        if region == 'ru':
            server = 'lesta'
        else:
            server = 'wg'
        nick_data = JsonUtils.read('ship_name_nick')
        main_data = JsonUtils.read(f'ship_name_{server}')
        ship_name_format: str = name_format(ship_name)
        if ship_name_format.endswith(('old','旧')):
            old = True
        else:
            old = False

        result = []
        exists_ids = []
        # 别名表匹配
        for ship_id, ship_data in nick_data[language].items():
            for index in ship_data:
                if ship_name_format == name_format(index):
                    result.append(data_format(ship_id, main_data)) 
                    return result
        for ship_id, ship_data in main_data.items():
            if ship_name_format == name_format(ship_data['ship_name']['en']):
                result.append(data_format(ship_id, main_data)) 
                return result
            if language in ['cn','ja','ru','en']:
                if language == 'en':
                    lang = 'en_l'
                else:
                    lang = language
                if ship_name_format == name_format(ship_data['ship_name'][lang]):
                    result.append(data_format(ship_id, main_data)) 
                    return result
        for ship_id, ship_data in main_data.items():
            if ship_name_format in name_format(ship_data['ship_name']['en']):
                if old == False and ship_id in GameData.OLD_SHIP_ID_LIST:
                    continue
                if ship_id not in exists_ids:
                    result.append(data_format(ship_id, main_data)) 
                    exists_ids.append(ship_id)
            if language in ['cn','ja','ru','en']:
                if language == 'en':
                    lang = 'en_l'
                else:
                    lang = language
                if ship_name_format in name_format(ship_data['ship_name'][lang]):
                    if old == False and ship_id in GameData.OLD_SHIP_ID_LIST:
                        continue
                    if ship_id not in exists_ids:
                        result.append(data_format(ship_id, main_data)) 
                        exists_ids.append(ship_id)
        return result
    
    @staticmethod
    def query_ship(region: str, query_condition: ShipFilter):
        """
        根据输入的查询条件返回对应的船只列表

        参数:
            query_condition
        """
        # query_condition = {
        #     'type': ['AirCarrier','Battleship','Cruiser','Destroyer','Submarine'],
        #     'tier': [1,2,3,4,5,6,7,8,9,10,11],
        #     'nation': ['commonwealth','europe','france','germany','italy','japan','netherlands','pan_america','pan_asia','spain','uk','usa','ussr']
        # }
        if region == 'ru':
            server = 'lesta'
        else:
            server = 'wg'
        ship_data = JsonUtils.read(f'ship_name_{server}')
        result = {}
        for ship_id, ship_info in ship_data.items():
            if query_condition.type and ship_info["type"] not in query_condition.type:
                continue
            if query_condition.tier and ship_info["tier"] not in [t.value for t in query_condition.tier]:
                continue
            if query_condition.nation and ship_info["nation"] not in [n.value for n in query_condition.nation]:
                continue
            result[ship_id] = ship_info
        return result
