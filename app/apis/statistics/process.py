from shard import RatingAlgo

from app.schemas import ShipProcessedData


def accumulate_overall(processed_data: dict, original_data: dict):
    if original_data['battles_count'] <= 0:
        return
    
    processed_data['battles'] += original_data['battles_count']
    processed_data['wins'] += original_data['wins']
    processed_data['damage'] += original_data['damage_dealt']
    processed_data['frags'] += original_data['frags']
    processed_data['exp'] += original_data['original_exp']

    if original_data['personal_rating'] == -1:
        return
    
    processed_data['v_battles'] += original_data['battles_count']
    processed_data['p_rating'] += original_data['personal_rating'] * original_data['battles_count']
    processed_data['d_rating'] += original_data['damage_rating'] * original_data['battles_count']
    processed_data['f_rating'] += original_data['frags_rating'] * original_data['battles_count']

def format_overall(processed_data: ShipProcessedData, show_eggshell: bool = False):
    result = {
        'battles': '-',
        'win_rate': '-',
        'avg_damage': '-',
        'avg_frags': '-',
        'avg_exp': '-',
        'rating': -1,
        'level': {
            'win_rate': 0,
            'avg_damage': 0,
            'avg_frags': 0
        }
    }
    if processed_data['battles'] == 0:
        return result
    
    result['battles'] = '{:,}'.format(processed_data['battles']).replace(',', ' ')
    result['win_rate'] = '{:.2f}%'.format(processed_data['wins']/processed_data['battles']*100)
    result['avg_damage'] = '{:,}'.format(int(processed_data['damage']/processed_data['battles'])).replace(',', ' ')
    result['avg_frags'] = '{:.2f}'.format(processed_data['frags']/processed_data['battles'])
    result['avg_exp'] = '{:,}'.format(int(processed_data['exp']/processed_data['battles'])).replace(',', ' ')

    result['level']['win_rate'] = RatingAlgo.get_metric_level(processed_data['wins']/processed_data['battles']*100, 'win_rate')
    
    if processed_data['v_battles'] == 0:
        return result
    
    result['rating'] = int(processed_data['p_rating']/processed_data['v_battles'])
    result['level']['avg_damage'] = RatingAlgo.get_metric_level(processed_data['d_rating']/processed_data['v_battles'], 'damage')
    result['level']['avg_frags'] = RatingAlgo.get_metric_level(processed_data['f_rating']/processed_data['v_battles'], 'frags')

    return result