from pydantic import BaseModel


class ClanBaseData(BaseModel):
    clan_id: int = None
    tag: str = None
    league: int = None

class UserBasicData(BaseModel):
    region_id: int = 0
    account_id: int = 0
    is_enabled: int = 0
    activity_level: int = 0
    is_public: int = 0
    username: str = ""
    register_time: int = None
    insignias: str = None
    total_battles: int = 0
    pvp_battles: int = 0
    ranked_battles: int = 0
    last_battle_at: int = 0
    clan: ClanBaseData = None
