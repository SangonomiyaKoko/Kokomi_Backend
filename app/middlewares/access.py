from fastapi import Security, HTTPException
from fastapi.security import APIKeyHeader
from enum import Enum
from typing import Optional

from app.core import EnvConfig
from app.utils import JsonUtils


class Role(str, Enum):
    ROOT = "root"
    USER = "user"
    MANAGER = "manager"
    VISITOR = "visitor"


class VisitorManager:
    """访客令牌管理器
    
    管理访客令牌列表，支持从 JSON 文件加载、热重载和持久化
    JSON 格式: {"token": "备注", "token2": "备注2"}
    """

    _tokens: dict[str, str] = {}
    
    @classmethod
    def init(cls) -> None:
        """从 JSON 文件加载访客令牌"""
        cls._tokens = JsonUtils.read('visitor_token')
    
    @classmethod
    def add(cls, token: str, remark: str = "") -> bool:
        """添加访客令牌"""
        if not token or token in cls._tokens:
            return False
        
        cls._tokens[token] = remark
        JsonUtils.write('visitor_token', cls._tokens)
        return True
    
    @classmethod
    def delete(cls, token: str) -> bool:
        """删除访客令牌"""
        if not token or token not in cls._tokens:
            return False
        
        del cls._tokens[token]
        JsonUtils.write('visitor_token', cls._tokens)
        return True
    
    @classmethod
    def contains(cls, token: str) -> bool:
        """检查令牌是否在访客列表中"""
        return token in cls._tokens
    
    @classmethod
    def get_all(cls) -> dict[str, str]:
        """获取所有访客令牌(仅查看，不可修改)"""
        return cls._tokens

class SecurityManager:
    _api_key_scheme = APIKeyHeader(name="Access-Token", auto_error=False)
    
    @classmethod
    def _get_config(cls):
        try:
            return EnvConfig.get_config()
        except RuntimeError:
            raise HTTPException(status_code=500, detail="Configuration not initialized")
    
    @classmethod
    def _validate_api_key(cls, api_key: Optional[str]) -> str:
        """验证 API Key 并返回角色"""
        if not api_key:
            raise HTTPException(status_code=403, detail="Missing Access Token")
        
        config = cls._get_config()
        
        if api_key == config.SECURITY.root:
            return Role.ROOT
        elif api_key == config.SECURITY.manager:
            return Role.MANAGER
        elif api_key == config.SECURITY.user:
            return Role.USER
        elif VisitorManager.contains(api_key):
            return Role.VISITOR
        else:
            raise HTTPException(status_code=403, detail="Invalid Access Token")
    
    @classmethod
    async def require_root(cls, api_key: str = Security(_api_key_scheme)) -> bool:
        """要求 Root 权限"""
        role = cls._validate_api_key(api_key)
        if role == Role.ROOT:
            return True
        raise HTTPException(status_code=403, detail="Root permission required")
    
    @classmethod
    async def require_user(cls, api_key: str = Security(_api_key_scheme)) -> bool:
        """要求 User 或 Root 权限"""
        role = cls._validate_api_key(api_key)
        if role in [Role.ROOT, Role.USER]:
            return True
        raise HTTPException(status_code=403, detail="User permission required")
    
    @classmethod
    async def require_user(cls, api_key: str = Security(_api_key_scheme)) -> bool:
        """要求 User 或 Root 权限"""
        role = cls._validate_api_key(api_key)
        if role in [Role.ROOT, Role.USER]:
            return True
        raise HTTPException(status_code=403, detail="User permission required")
    
    @classmethod
    async def require_manager(cls, api_key: str = Security(_api_key_scheme)) -> bool:
        """要求 User 或 Root 权限"""
        role = cls._validate_api_key(api_key)
        if role in [Role.ROOT, Role.MANAGER]:
            return True
        raise HTTPException(status_code=403, detail="User permission required")
    
    @classmethod
    async def require_vistor(cls, api_key: str = Security(_api_key_scheme)) -> bool:
        """要求 Visitor、User 或者 Root 权限"""
        role = cls._validate_api_key(api_key)
        if role in [Role.ROOT, Role.VISITOR]:
            return True
        raise HTTPException(status_code=403, detail="Visitor permission required")
    
    @classmethod
    async def get_current_role(cls, api_key: str = Security(_api_key_scheme)) -> str:
        """获取当前用户角色"""
        return cls._validate_api_key(api_key)