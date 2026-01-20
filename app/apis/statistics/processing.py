from typing import Dict

from app.utils import RatingUtils
from app.schemas import ShipDataDict, ShipInfoDict


NoneProcessedData = {
    'battles_count': 0,
    'wins': 0,
    'damage_dealt': 0,
    'frags': 0,
    'original_exp': 0,
    'value_battles_count': 0,
    'personal_rating': 0,
    'n_damage_dealt': 0,
    'n_frags': 0
}

ProcessedData = {
    'battles_count': 0,
    'win_rate': 0.0,
    'avg_damage': 0,
    'avg_frags': 0.0,
    'avg_exp': 0,
    'rating': 0,
    'rating_next': 0,
    'win_rate_class': 0,
    'avg_damage_class': 0,
    'avg_frags_class': 0,
    'rating_class': 0
}

def pvp_calculate_rating(region: str, data: Dict[str, Dict], server_data: dict):
    for ship_id, ship_data in data.items():
        for key in ['pvp', 'pvp_solo', 'pvp_div2', 'pvp_div3']:
            RatingUtils.get_rating_by_data(
                key,
                ship_data[key],
                server_data.get(ship_id).get(region)
            )
    return data

def processing_overall_data(data: Dict[str, Dict], field: str):
    original_data = NoneProcessedData.copy()
    for _, ship_info in data.items():
        ship_data: ShipDataDict = ship_info[field]
        if ship_data == {}:
            continue
        for key in ['battles_count','wins','damage_dealt','frags','original_exp']:
            original_data[key] += ship_data[key]
        if ship_data['personal_rating'] != -1:
            original_data['value_battles_count'] += ship_data['battles_count']
            original_data['personal_rating'] += ship_data['personal_rating']
            original_data['n_damage_dealt'] += ship_data['damage_rating']
            original_data['n_frags'] += ship_data['frags_rating']
    result = ProcessedData.copy()
    if original_data['battles_count'] == 0:
        result['battles_count'] = '-'
        result['win_rate'] = '-'
        result['avg_damage'] = '-'
        result['avg_frags'] = '-'
        result['avg_exp'] = '-'
        result['rating'] = '-1'
        result['rating_next'] = '1'
    else:
        result['battles_count'] = original_data['battles_count']
        result['win_rate'] = round(original_data['wins']/original_data['battles_count']*100,2)
        result['avg_damage'] = int(original_data['damage_dealt']/original_data['battles_count'])
        result['avg_frags'] = round(original_data['frags']/original_data['battles_count'],2)
        result['avg_exp'] = int(original_data['original_exp']/original_data['battles_count'])
        if original_data['value_battles_count'] != 0:
            result['rating'] = int(original_data['personal_rating']/original_data['value_battles_count'])
            rating_class, rating_next = RatingUtils.get_rating_class(result['rating'],True)
            result['rating_next'] = str(rating_next)
            result['win_rate_class'] = RatingUtils.get_content_class(0, result['win_rate'])
            result['avg_damage_class'] = RatingUtils.get_content_class(1, original_data['n_damage_dealt']/original_data['value_battles_count'])
            result['avg_frags_class'] = RatingUtils.get_content_class(2, original_data['n_frags']/original_data['value_battles_count'])
            result['rating_class'] = rating_class
        else:
            result['rating'] = -1
            rating_class, rating_next = RatingUtils.get_rating_class(-1,True)
            result['rating_next'] = str(rating_next)
            result['win_rate_class'] = RatingUtils.get_content_class(0, -1)
            result['avg_damage_class'] = RatingUtils.get_content_class(1, -1)
            result['avg_frags_class'] = RatingUtils.get_content_class(2, -1)
            result['rating_class'] = rating_class
        result['battles_count'] = '{:,}'.format(result['battles_count']).replace(',', ' ')
        result['win_rate'] = '{:.2f}%'.format(result['win_rate'])
        result['avg_damage'] = '{:,}'.format(result['avg_damage']).replace(',', ' ')
        result['avg_frags'] = '{:.2f}'.format(result['avg_frags'])
        result['avg_exp'] = '{:,}'.format(result['avg_exp']).replace(',', ' ')
        result['rating'] = '{:,}'.format(result['rating']).replace(',', ' ')
    return result

def processing_battle_type_data(data: Dict[str, Dict]):
    original_data = {
        'pvp_solo': NoneProcessedData.copy(),
        'pvp_div2': NoneProcessedData.copy(),
        'pvp_div3': NoneProcessedData.copy()
    }
    for _, ship_info in data.items():
        for field in ['pvp_solo', 'pvp_div2', 'pvp_div3']:
            ship_data: ShipDataDict = ship_info[field]
            if ship_data == {}:
                continue
            for key in ['battles_count','wins','damage_dealt','frags','original_exp']:
                original_data[field][key] += ship_data[key]
            if ship_data['personal_rating'] != -1:
                original_data[field]['value_battles_count'] += ship_data['battles_count']
                original_data[field]['personal_rating'] += ship_data['personal_rating']
                original_data[field]['n_damage_dealt'] += ship_data['damage_rating']
                original_data[field]['n_frags'] += ship_data['frags_rating']
    result = {
        'pvp_solo': ProcessedData.copy(),
        'pvp_div2': ProcessedData.copy(),
        'pvp_div3': ProcessedData.copy()
    }
    for field in ['pvp_solo', 'pvp_div2', 'pvp_div3']:
        if original_data[field]['battles_count'] == 0:
            result[field]['battles_count'] = '-'
            result[field]['win_rate'] = '-'
            result[field]['avg_damage'] = '-'
            result[field]['avg_frags'] = '-'
            result[field]['avg_exp'] = '-'
            result[field]['rating'] = '-1'
            result[field]['rating_next'] = '1'
        else:
            result[field]['battles_count'] = original_data[field]['battles_count']
            result[field]['win_rate'] = round(original_data[field]['wins']/original_data[field]['battles_count']*100,2)
            result[field]['avg_damage'] = int(original_data[field]['damage_dealt']/original_data[field]['battles_count'])
            result[field]['avg_frags'] = round(original_data[field]['frags']/original_data[field]['battles_count'],2)
            result[field]['avg_exp'] = int(original_data[field]['original_exp']/original_data[field]['battles_count'])
            if original_data[field]['value_battles_count'] != 0:
                result[field]['rating'] = int(original_data[field]['personal_rating']/original_data[field]['value_battles_count'])
                rating_class, rating_next = RatingUtils.get_rating_class(result[field]['rating'])
                result[field]['rating_next'] = str(rating_next)
                result[field]['win_rate_class'] = RatingUtils.get_content_class(0, result[field]['win_rate'])
                result[field]['avg_damage_class'] = RatingUtils.get_content_class(1, original_data[field]['n_damage_dealt']/original_data[field]['value_battles_count'])
                result[field]['avg_frags_class'] = RatingUtils.get_content_class(2, original_data[field]['n_frags']/original_data[field]['value_battles_count'])
                result[field]['rating_class'] = rating_class
            else:
                result[field]['rating'] = -1
                rating_class, rating_next = RatingUtils.get_rating_class(-1)
                result[field]['rating_next'] = str(rating_next)
                result[field]['win_rate_class'] = RatingUtils.get_content_class(0, -1)
                result[field]['avg_damage_class'] = RatingUtils.get_content_class(1, -1)
                result[field]['avg_frags_class'] = RatingUtils.get_content_class(2, -1)
                result[field]['rating_class'] = rating_class
            result[field]['battles_count'] = '{:,}'.format(result[field]['battles_count']).replace(',', ' ')
            result[field]['win_rate'] = '{:.2f}%'.format(result[field]['win_rate'])
            result[field]['avg_damage'] = '{:,}'.format(result[field]['avg_damage']).replace(',', ' ')
            result[field]['avg_frags'] = '{:.2f}'.format(result[field]['avg_frags'])
            result[field]['avg_exp'] = '{:,}'.format(result[field]['avg_exp']).replace(',', ' ')
            result[field]['rating'] = '{:,}'.format(result[field]['rating']).replace(',', ' ')
    return result

def processing_ship_type_data(data: Dict[str, Dict], battle_field: str, shipid_data: dict):
    original_data = {
        'AirCarrier': NoneProcessedData.copy(),
        'Battleship': NoneProcessedData.copy(),
        'Cruiser': NoneProcessedData.copy(),
        'Destroyer': NoneProcessedData.copy(),
        'Submarine': NoneProcessedData.copy()
    }
    for ship_id, ship_info in data.items():
        ship_data: ShipDataDict = ship_info[battle_field]
        if ship_data == {}:
            continue
        field = shipid_data.get(ship_id).get('type')
        if field is None:
            continue
        for key in ['battles_count','wins','damage_dealt','frags','original_exp']:
            original_data[field][key] += ship_data[key]
        if ship_data['personal_rating'] != -1:
            original_data[field]['value_battles_count'] += ship_data['battles_count']
            original_data[field]['personal_rating'] += ship_data['personal_rating']
            original_data[field]['n_damage_dealt'] += ship_data['damage_rating']
            original_data[field]['n_frags'] += ship_data['frags_rating']
    result = {
        'AirCarrier': ProcessedData.copy(),
        'Battleship': ProcessedData.copy(),
        'Cruiser': ProcessedData.copy(),
        'Destroyer': ProcessedData.copy(),
        'Submarine': ProcessedData.copy()
    }
    for field in ['AirCarrier', 'Battleship', 'Cruiser', 'Destroyer', 'Submarine']:
        if original_data[field]['battles_count'] == 0:
            result[field]['battles_count'] = '-'
            result[field]['win_rate'] = '-'
            result[field]['avg_damage'] = '-'
            result[field]['avg_frags'] = '-'
            result[field]['avg_exp'] = '-'
            result[field]['rating'] = '-1'
            result[field]['rating_next'] = '1'
        else:
            result[field]['battles_count'] = original_data[field]['battles_count']
            result[field]['win_rate'] = round(original_data[field]['wins']/original_data[field]['battles_count']*100,2)
            result[field]['avg_damage'] = int(original_data[field]['damage_dealt']/original_data[field]['battles_count'])
            result[field]['avg_frags'] = round(original_data[field]['frags']/original_data[field]['battles_count'],2)
            result[field]['avg_exp'] = int(original_data[field]['original_exp']/original_data[field]['battles_count'])
            if original_data[field]['value_battles_count'] != 0:
                result[field]['rating'] = int(original_data[field]['personal_rating']/original_data[field]['value_battles_count'])
                rating_class, rating_next = RatingUtils.get_rating_class(result[field]['rating'])
                result[field]['rating_next'] = str(rating_next)
                result[field]['win_rate_class'] = RatingUtils.get_content_class(0, result[field]['win_rate'])
                result[field]['avg_damage_class'] = RatingUtils.get_content_class(1, original_data[field]['n_damage_dealt']/original_data[field]['value_battles_count'])
                result[field]['avg_frags_class'] = RatingUtils.get_content_class(2, original_data[field]['n_frags']/original_data[field]['value_battles_count'])
                result[field]['rating_class'] = rating_class
            else:
                result[field]['rating'] = -1
                rating_class, rating_next = RatingUtils.get_rating_class(-1)
                result[field]['rating_next'] = str(rating_next)
                result[field]['win_rate_class'] = RatingUtils.get_content_class(0, -1)
                result[field]['avg_damage_class'] = RatingUtils.get_content_class(1, -1)
                result[field]['avg_frags_class'] = RatingUtils.get_content_class(2, -1)
                result[field]['rating_class'] = rating_class
            result[field]['battles_count'] = '{:,}'.format(result[field]['battles_count']).replace(',', ' ')
            result[field]['win_rate'] = '{:.2f}%'.format(result[field]['win_rate'])
            result[field]['avg_damage'] = '{:,}'.format(result[field]['avg_damage']).replace(',', ' ')
            result[field]['avg_frags'] = '{:.2f}'.format(result[field]['avg_frags'])
            result[field]['avg_exp'] = '{:,}'.format(result[field]['avg_exp']).replace(',', ' ')
            result[field]['rating'] = '{:,}'.format(result[field]['rating']).replace(',', ' ')
    return result

def processing_pvp_chart(data: Dict[str, Dict], shipid_data: dict):
    result = [[0,0,0,0,0] for _ in range(11)]
    for ship_id, ship_info in data.items():
        ship_data: ShipDataDict = ship_info['pvp']
        if ship_data == {}:
            continue
        ship_name:ShipInfoDict = shipid_data.get(ship_id)
        if ship_name is None:
            continue
        ship_tier = ship_name['tier']
        ship_type = ship_name['type']
        ship_type_dict = {
            'AirCarrier': 0,
            'Battleship': 1,
            'Cruiser': 2,
            'Destroyer': 3,
            'Submarine': 4
            }
        result[ship_tier-1][ship_type_dict[ship_type]] += ship_data['battles_count']
    return result