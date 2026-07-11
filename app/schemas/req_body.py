from pydantic import BaseModel, Field


class VisitorToken(BaseModel):
    token: str = Field(...)
    remark: str = Field(...)

class AuthToken(BaseModel):
    account_id: int = Field(...)
    access_token: str = Field(...)
    expires_at: int = Field(...)
    
class AccessToken(BaseModel):
    account_id: int = Field(...)
    access_token: str = Field(...)

