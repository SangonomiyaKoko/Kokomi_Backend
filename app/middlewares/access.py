from typing import Literal
from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader

from app.core import EnvConfig, split_config


Role = Literal["root", "user"]

api_key_scheme = APIKeyHeader(name="Access-Token", auto_error=False)

def get_role(api_key: str = Security(api_key_scheme)) -> Role:
    if api_key in split_config(EnvConfig.get_config().ROOT_API_TOKEN):
        return "root"
    if api_key in split_config(EnvConfig.get_config().USER_API_TOKEN):
        return "user"
    raise HTTPException(status_code=403, detail="Invalid Access Token")

def require_user(role: Role = Security(get_role)) -> Role:
    return role

def require_root(role: Role = Security(get_role)) -> Role:
    if role != "root":
        raise HTTPException(status_code=403, detail="Root permission required")
    return role