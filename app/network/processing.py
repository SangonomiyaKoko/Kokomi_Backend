from app.constants import GameData


def processing_user_basic(user_basic: dict):
    data = {
        'pve': 0 if user_basic['pve'] == {} else user_basic['pve']['battles_count'],
        'pvp': 0 if user_basic['pvp'] == {} else user_basic['pvp']['battles_count'],
        'pvp_solo': 0 if user_basic['pvp_solo'] == {} else user_basic['pvp_solo']['battles_count'],
        'pvp_div2': 0 if user_basic['pvp_div2'] == {} else user_basic['pvp_div2']['battles_count'],
        'pvp_div3': 0 if user_basic['pvp_div3'] == {} else user_basic['pvp_div3']['battles_count'],
        'rank_solo': 0 if user_basic['rank_solo'] == {} else user_basic['rank_solo']['battles_count'],
        'rank_old': 0,
        'clan': 0,
        'oper': 0
    }
    for bt in ['rank_div2', 'rank_div3', 'rank_old_solo', 'rank_old_div2', 'rank_old_div3']:
        if user_basic[bt] != {}:
            data['rank_old'] += user_basic[bt]['battles_count']
    return data

def processing_season(season_data: dict, rank_data: dict) -> dict:
    result = {}
    for season_index in season_data:
        if 'rating_solo' in season_data[str(season_index)]:
            continue 
        if len(season_index) != 4:
            continue
        result[season_index] = {
            'battles_count': 0, 
            'wins': 0, 
            'damage_dealt': 0,
            'frags': 0, 
            'original_exp': 0, 
            'best_season_rank': 3, 
            'best_rank': 10
        }
        for index in ['battles_count', 'wins', 'damage_dealt', 'frags', 'original_exp']:
            if season_index in ['1001','1002','1003']:
                result[season_index][index] = season_data[str(season_index)]['-1']['rank_solo'][index]
            else:
                result[season_index][index] = season_data[str(season_index)]['0']['rank_solo'][index]
        for _, season_stage_data in rank_data[season_index].items():
            for num in [1, 2, 3]:
                if str(num) in season_stage_data:
                    if result[season_index]['best_season_rank'] > num:
                        result[season_index]['best_season_rank'] = num
                        result[season_index]['best_rank'] = season_stage_data[str(num)]['rank_best']
                        continue
                    elif (
                        result[season_index]['best_season_rank'] == num
                        and result[season_index]['best_rank'] > season_stage_data[str(num)]['rank_best']
                    ):
                        result[season_index]['best_rank'] = season_stage_data[str(num)]['rank_best']
                        continue
                    continue
                else:
                    continue
    sorted_dict = dict(sorted(result.items(), reverse=True))
    return sorted_dict

def processing_pvp_data(responses: list, fields: list, include_old: bool):
    # 处理pvp数据，支持pvp_solo/pvp_div2/pvp_div3
    result = {}
    record = {
        'max_damage_dealt': 0,
        'max_frags': 0,
        'max_exp': 0,
        'max_planes_killed': 0,
        'max_scouting_damage': 0,
        'max_total_agro': 0
    }
    for i in range(len(fields)):
        response = responses[i]
        field = fields[i]
        for ship_id, ship_data in response.items():
            if include_old is False and ship_id in GameData.OLD_SHIP_ID_LIST:
                continue
            field_data = ship_data[field]
            if field_data == {}:
                continue
            if ship_id not in result:
                result[ship_id] = {
                    'pvp': {
                        'battles_count': 0,
                        'wins': 0,
                        'damage_dealt': 0,
                        'frags': 0,
                        'original_exp': 0,
                        'personal_rating': 0,
                        'damage_rating': 0,
                        'frags_rating': 0
                    },
                    'pvp_solo': {},
                    'pvp_div2': {},
                    'pvp_div3': {}
                }
            for key in ['battles_count','wins','damage_dealt','frags','original_exp']:
                result[ship_id]['pvp'][key] += field_data[key]
                result[ship_id][field][key] = field_data[key]
            for key in ['max_damage_dealt','max_frags','max_exp','max_planes_killed','max_scouting_damage','max_total_agro']:
                if field_data[key] > record[key]:
                    record[key] = field_data[key]
    return result, record

def processing_cb_season(data: dict):
    result = []
    battleCount = 0
    wins = 0
    damage = 0 # 总伤害
    frags = 0
    exp = 0
    for i in data["seasons"]:
        seasonId = i["season_id"]
        if seasonId >= 100:
            continue
        season = {}
        season["season_id"] = seasonId
        battles = i["battles_count"]
        battleCount += battles
        season["battles"] = battles
        win = i["wins"]
        wins+= win
        season["winrate"] = round(win / battles * 100, 2)
        damage1 = i["damage_dealt"]
        damage += damage1
        season["avg_damage"] =  damage1 // battles
        kill = i["frags"]
        frags += kill
        season["avg_frags"] = round(kill / battles, 2)
        ixp = i["xp"]
        exp += ixp
        season["avg_exp"] = ixp // battles
        result.append(season)
    total = {}
    total["battles_count"] = battleCount
    total["win_rate"] = round(wins / battleCount * 100, 2)
    total["avg_damage"] = damage // battleCount
    total["avg_frags"] = round(frags / battleCount, 2) 
    total["avg_exp"] = exp // battleCount
    result.sort(key=lambda x: x['season_id'], reverse=True)
    return total, result

def processing_cb_achieve(region: str, response: dict):
    result = {
        0: 0,
        1: 0,
        2: 0,
        3: 0,
        4: 0
    }
    if response is None:
        return result
    if region == 'ru':
        realm_data = GameData.LESTA_CLAN_SEAESON_LIST
    else:
        realm_data = GameData.WG_CLAN_SEAESON_LIST
    for index, count in response['battle'].items():
        if index in realm_data:
            result[realm_data[index]] += count
    return result

def processing_cb_seasons(data: dict):
    result = []
    for i in data["seasons"]:
        seasonId = i["season_id"]
        if seasonId >= 100:
            continue
        season = {
            'season_id': seasonId,
            'battles_count': i["battles"],
            'wins': i["wins"],
            'damage_dealt': i["damage_dealt"],
            'frags': i['frags'],
            'original_exp': i["xp"]
        }
        result.append(season)
    return result