from typing_extensions import TypedDict


class ShipDataDict(TypedDict):
    battles_count: int
    wins: int
    damage_dealt: int
    frags: int
    original_exp: int
    personal_rating: int
    damage_rating: int
    frags_rating: int

class ServerDataDict(TypedDict):
    battles_count: int
    win_rate: float
    avg_damage: float
    avg_frags: float
    avg_exp: float
    survived_rate: float
    avg_scouting_damage: float
    avg_art_agro: float
    avg_planes_killed: float

class ShipNameDict(TypedDict):
    cn: str
    en: str
    en_l: str
    ja: str
    ru: str

class ShipInfoDict(TypedDict):
    tier: int
    type: str
    nation: str
    premium: bool
    special: bool
    index: str
    ship_name: ShipNameDict