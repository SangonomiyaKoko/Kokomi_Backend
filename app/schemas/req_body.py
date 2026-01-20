from typing import List, Optional, Union, Literal
from pydantic import BaseModel, Field

from .req_params import (
    ShipTier, ShipType, ShipNation,
    Platform, Region
)

class ShipFilter(BaseModel):
    type: Optional[List[ShipType]] = Field(None, min_length=1)
    tier: Optional[List[ShipTier]] = Field(None, min_items=1)
    nation: Optional[List[ShipNation]] = Field(None, min_items=1)

class BindByIGN(BaseModel):
    type: Literal["ign"]
    region: Region = Field(default=Region.ASIA)
    ign: str = Field(...)

class BindByUID(BaseModel):
    type: Literal["uid"]
    region: Region = Field(default=Region.ASIA)
    uid: int = Field(...)

BindBody = Union[BindByUID, BindByIGN]

class AuthResponse(BaseModel):
    status: str
    account_id: int
    nickname: str
    access_token: str
    expires_at: int
    
class ACResponse(BaseModel):
    account_id: int = Field(...)
    access_token: str = Field(...)
    
class UserInfo(BaseModel):
    platform: Platform = Field(default=Platform.QQ_BOT)
    user_id: str = Field(...)
    
class EnabelRecent(BaseModel):
    platform: Platform = Field(default=Platform.QQ_BOT)
    user_id: str = Field(...)
    region: Region = Field(default=Region.ASIA)
    uid: int = Field(...)

