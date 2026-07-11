from fastapi import HTTPException, APIRouter, Query, Path

from app.core import EnvConfig, AppState
from app.schemas import AccessToken
from app.apis.platform import TokenAPI, SearchAPI, RefreshAPI
from app.response import JSONResponse
from app.utils import GameUtils

router = APIRouter(prefix="/platform")

@router.get("/search/user/", summary="搜索游戏用户")
async def searchUser(
    name: str = Query(..., description="用户昵称")
):
    """搜索游戏用户

    通过用户昵称搜索用户，返回搜索结果列表。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ✅ **维护模式**: ❌
    """
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if 2 < len(name) < 25:
        result = await SearchAPI.search_user(name)
        return result
    else:
        raise HTTPException(status_code=422, detail="Invalid tag length (2-25 required)")

@router.get("/search/clan/", summary="搜索游戏工会")
async def searchClan(
    tag: str = Query(..., description="工会标签")
):
    """搜索游戏工会

    通过工会标签搜索工会，返回搜索结果列表。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ✅ **维护模式**: ❌
    """
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if 1 < len(tag) < 9:
        result = await SearchAPI.search_clan(tag)
        return result
    else:
        raise HTTPException(status_code=422, detail="Invalid tag length (2-8 required)")


@router.patch("/user/{user_id}/", summary="刷新用户基本信息的缓存")
async def getUserBasic(user_id: int = Path(...)):
    """刷新用户基本信息的缓存

    排行榜系统基于用户在本地的缓存数据进行计算，因此和最新数据存在不同步情况，如需立即更新可以通过此接口手动触发。
    
    该指令会调用接口更新用户的基本信息，同时将该用户标记为缓存待刷新状态，每隔 10 分钟刷新一次，并同步更新排行榜数据。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await RefreshAPI.refresh_user(user_id)

@router.post("/token/access/", summary="设置用户 Access-Token 数据")
async def setAccessToken(token: AccessToken):
    """设置用户 Access-Token 数据

    先检测传入Token是否有效，如有效则写入数据库，主要用于隐藏战绩用户的查询参数。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    return await TokenAPI.set_ac(token.account_id, token.access_token)

@router.delete("/token/access/", summary="删除用户 Access-Token 数据")
async def delAccessToken(account_id: int):
    """删除用户 Access-Token 数据

    先检测传入Token是否有效，如有效则写入数据库，主要用于隐藏战绩用户的查询参数。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    return await TokenAPI.del_ac(account_id)

# @router.post("/token/auth/", summary="设置auth")
# async def setAuthToken(auth: AuthResponse):
#     result = await TokenAPI.set_auth(auth.account_id, auth.access_token, auth.expires_at)
#     return result

# @router.delete("/token/auth/", summary="删除auth")
# async def delAuthToken(account_id: int):
#     result = await TokenAPI.del_auth(account_id)
#     return result
