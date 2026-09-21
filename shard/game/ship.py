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
