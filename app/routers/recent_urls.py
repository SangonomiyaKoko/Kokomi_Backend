from fastapi import HTTPException, APIRouter, Query, Path

from app.core import EnvConfig, AppState
from app.response import JSONResponse
from app.apis.recent import RecentAPI
from app.middlewares import BlacklistManager
from app.utils import GameUtils

router = APIRouter(prefix='/recent')

@router.get("/users/{user_id}/summary/", summary="获取用户近期数据概览")
async def getRecentSummary(
    user_id: int = Path(..., description="用户ID"),
):
    """获取用户近期数据概览

    返回用户近期数据库文件基本信息的概览。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if BlacklistManager.is_user_blocked(user_id):
        return JSONResponse.API_UseInBlacklist
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    result = await RecentAPI.summary(user_id)

    return result

@router.post("/users/{user_id}/recent/", summary="启用用户记录数据功能")
async def getRecentSummary(
    user_id: int = Path(..., description="用户ID"),
):
    """启用用户记录数据功能

    先效验用户是否符合条件，再启用用户记录近期数据功能。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if BlacklistManager.is_user_blocked(user_id):
        return JSONResponse.API_UseInBlacklist
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    result = await RecentAPI.enable(user_id)

    return result

@router.get("/users/{user_id}/recent/", summary="获取用户近期数据")
async def getRecentSummary(
    user_id: int = Path(..., description="用户ID"),
    days: int = Query(..., ge=1, le=500, description="时间间隔")
):
    """获取用户近期数据

    先效验用户是否符合条件，再启用用户记录近期数据功能。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if BlacklistManager.is_user_blocked(user_id):
        return JSONResponse.API_UseInBlacklist
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    result = await RecentAPI.recent(user_id, days)

    return result

@router.get("/users/{user_id}/recent/plus/", summary="获取用户近期数据(Plus)")
async def getRecentSummary(
    user_id: int = Path(..., description="用户ID")
):
    """获取用户近期数据

    先效验用户是否符合条件，再启用用户记录近期数据功能。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if BlacklistManager.is_user_blocked(user_id):
        return JSONResponse.API_UseInBlacklist
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    result = await RecentAPI.recents(user_id)

    return result

# @router.get("/users/{user_id}/random/", summary="获取用户近期随机数据")
# async def getRandomRecent(
#     user_id: int = Path(..., description="用户ID"),
# ):
#     if EnvConfig.DEV_MODE:
#         return JSONResponse.API_2018_Maintenance
    
#     if GameUtils.check_uid(user_id) == False:
#         return JSONResponse.API_2001_IllegalAccountID
    
#     result = await RecentAPI.ranked(user_id, None, None)

#     return result

# @router.get("/users/{user_id}/ranked/", summary="获取用户近期排位数据")
# async def getRankedRecent(
#     user_id: int = Path(..., description="用户ID"),
# ):
#     if EnvConfig.DEV_MODE:
#         return JSONResponse.API_2018_Maintenance
    
#     if GameUtils.check_uid(user_id) == False:
#         return JSONResponse.API_2001_IllegalAccountID
    
#     result = await RecentAPI.ranked(user_id, None, None)

#     return result