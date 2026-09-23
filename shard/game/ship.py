class ShipMaps:
    """舰船属性与统计指标对应的接口 ID 映射"""

    # 定义接口字段对应的 ID
    SHIP_TYPE_MAP = {
        "AirCarrier": 1,
        "Battleship": 2,
        "Cruiser": 3,
        "Destroyer": 4,
        "Submarine": 5
    }
    SHIP_NATION_MAP = {
        "usa": 1,
        "japan": 2,
        "germany": 3,
        "uk": 4,
        "ussr": 5,
        "france": 6,
        "italy": 7,
        "pan_asia": 8,
        "europe": 9,
        "netherlands": 10,
        "commonwealth": 11,
        "pan_america": 12,
        "spain": 13
    }
    SHIP_RARITY_MAP = {
        "Common": 1,
        "Uncommon": 2,
        "Rare": 3,
        "Epic": 4,
        "Legendary": 5
    }
    SHIP_METRIC_MAP = {
        "battles": 1,
        "wins": 2,
        "damage": 3,
        "frags": 4,
        "exp": 5,
        "survived": 6,
        "scouting_dmg": 7,
        "potential_dmg": 8,
        "planes": 9,
        "rating": 10
    }
    
class GameData:
    SHIP_TYPE_MAP = {
        1: 'AirCarrier',
        2: 'Battleship',
        3: 'Cruiser',
        4: 'Destroyer',
        5: 'Submarine'
    }
    SHIP_NATION_MAP = {
        1: 'usa',
        2: 'japan',
        3: 'germany',
        4: 'uk',
        5: 'ussr',
        6: 'france',
        7: 'italy',
        8: 'pan_asia',
        9: 'europe',
        10: 'netherlands',
        11: 'commonwealth',
        12: 'pan_america',
        13: 'spain'
    }
    WG_CLAN_SEAESON_LIST = {
        'PCH161_CLAN_LEAGUE_4': 4,
        'PCH160_CLAN_LEAGUE_3': 3,
        'PCH159_CLAN_LEAGUE_2': 2,
        'PCH158_CLAN_LEAGUE_1': 1,
        'PCH162_CLAN_LEAGUE_TOP': 0,
        'PCH177_TopLeagueClanSeason_2': 0,
        'PCH192_TopLeagueClanSeason_3': 0,
        'PCH210_TopLeagueClanSeason_4': 0,
        'PCH233_TopLeagueClanSeason_5': 0,
        'PCH243_TopLeagueClanSeason_6': 0,
        'PCH246_TopLeagueClanSeason_7': 0,
        'PCH251_TopLeagueClanSeason_8': 0,
        'PCH256_TopLeagueClanSeason_9': 0,
        'PCH260_TopLeagueClanSeason_10': 0,
        'PCH267_TopLeagueClanSeason_11': 0,
        'PCH283_TopLeagueClanSeason_12': 0,
        'PCH299_TopLeagueClanSeason_13': 0,
        'PCH315_TopLeagueClanSeason_14': 0,
        'PCH317_TopLeagueClanSeason_15': 0,
        'PCH319_TopLeagueClanSeason_16': 0,
        'PCH311_TopLeagueClanSeason_17': 0,
        'PCH391_TopLeagueClanSeason_18': 0,
        'PCH325_TopLeagueClanSeason_19': 0,
        'PCH327_TopLeagueClanSeason_20': 0,
        'PCH329_TopLeagueClanSeason_21': 0,
        'PCH331_TopLeagueClanSeason_22': 0,
        'PCH333_TopLeagueClanSeason_23': 0,
        'PCH335_TopLeagueClanSeason_24': 0,
        'PCH416_TopLeagueClanSeason_25': 0,
        'PCH418_TopLeagueClanSeason_26': 0,
        'PCH423_TopLeagueClanSeason_27': 0,
        'PCH432_TopLeagueClanSeason_28': 0,
        'PCH436_TopLeagueClanSeason_29': 0,
        'PCH439_TopLeagueClanSeason_30': 0,
        'PCH441_TopLeagueClanSeason_31': 0,
        'PCH443_TopLeagueClanSeason_32': 0
    }

    LESTA_CLAN_SEAESON_LIST = {
        'PCH161_CLAN_LEAGUE_4': 4,
        'PCH160_CLAN_LEAGUE_3': 3,
        'PCH159_CLAN_LEAGUE_2': 2,
        'PCH158_CLAN_LEAGUE_1': 1,
        'PCH162_CLAN_LEAGUE_TOP': 0,
        'PCH177_TopLeagueClanSeason_2': 0,
        'PCH192_TopLeagueClanSeason_3': 0,
        'PCH210_TopLeagueClanSeason_4': 0,
        'PCH233_TopLeagueClanSeason_5': 0,
        'PCH243_TopLeagueClanSeason_6': 0,
        'PCH246_TopLeagueClanSeason_7': 0,
        'PCH251_TopLeagueClanSeason_8': 0,
        'PCH256_TopLeagueClanSeason_9': 0,
        'PCH260_TopLeagueClanSeason_10': 0,
        'PCH267_TopLeagueClanSeason_11': 0,
        'PCH283_TopLeagueClanSeason_12': 0,
        'PCH299_TopLeagueClanSeason_13': 0,
        'PCH315_TopLeagueClanSeason_14': 0,
        'PCH317_TopLeagueClanSeason_15': 0,
        'PCH319_TopLeagueClanSeason_16': 0,
        'PCH311_TopLeagueClanSeason_17': 0,
        'PCH391_TopLeagueClanSeason_18': 0,
        'PCH325_TopLeagueClanSeason_19': 0,
        'PCH327_TopLeagueClanSeason_20': 0,
        'PCH329_TopLeagueClanSeason_21': 0,
        'PCH331_TopLeagueClanSeason_22': 0,
        'PCH333_TopLeagueClanSeason_23': 0,
        'PCH335_TopLeagueClanSeason_24': 0,
        'PCH417_TopLeagueClanSeason_25': 0,
        'PCH419_TopLeagueClanSeason_26': 0,
        'PCH421_TopLeagueClanSeason_27': 0,
        'PCH423_TopLeagueClanSeason_28': 0,
    }