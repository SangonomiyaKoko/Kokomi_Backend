from fastapi import HTTPException, APIRouter, Query, Path
from typing import Optional

from app.core import AppState, EnvConfig
from app.response import JSONResponse
from app.utils import GameUtils
from app.middlewares import BlacklistManager
from app.schemas import ShipTier, ShipType, ShipNation, PVPField
from app.apis.statistics import PVEAPI, RandomAPI, RankedAPI


router = APIRouter(prefix='/stats')

@router.get("/users/{user_id}/pve/overall/", summary="获取用户人机战斗总体数据")
async def getPvEOverall(
    user_id: int = Path(..., description="用户ID"),
    include_old: Optional[bool] = Query(None, description="是否包含旧船数据")
):
    """获取用户人机战斗总体数据
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ✅ **维护模式**: ❌
    """
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if BlacklistManager.is_user_blocked(user_id):
        return JSONResponse.API_UseInBlacklist
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    if include_old is None:
        include_old = True

    return await PVEAPI.overall(user_id, include_old)

@router.get("/users/{user_id}/random/overall/", summary="获取用户随机战斗总体数据")
async def getPvPOverall(
    user_id: int = Path(..., description="用户ID"),
    field: Optional[PVPField] = Query(None, description="数据类型"),
    ship_tier: Optional[ShipTier] = Query(None, description="船只等级"),
    ship_type: Optional[ShipType] = Query(None, description="船只类型"),
    ship_nation: Optional[ShipNation] = Query(None, description="船只国籍"),
    include_old: Optional[bool] = Query(None, description="是否包含旧船数据")
):
    """获取用户随机战斗总体数据

    返回指定筛选条件下的用户随机战斗总体数据，仅允许0-1个筛选条件，不支持多个参数。
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ✅ **维护模式**: ❌
    """
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if BlacklistManager.is_user_blocked(user_id):
        return JSONResponse.API_UseInBlacklist
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    if include_old is None:
        include_old = True
    
    filter_params = {
        "field": field,
        "tier": ship_tier,
        "type": ship_type,
        "nation": ship_nation
    }
    provided_filters = [name for name, val in filter_params.items() if val is not None]
    if len(provided_filters) > 1:
        raise HTTPException(status_code=422, detail="Only one filter allowed")
    
    if not provided_filters:
        filter_type = "overall"
    else:
        filter_field = provided_filters[0]
        filter_value = filter_params[filter_field]
        if filter_field == 'field':
            filter_type = filter_value.value.upper()
        elif filter_field == 'tier':
            filter_type = GameUtils.format_tier(filter_value.value)
        elif filter_field == 'nation':
            filter_type = GameUtils.format_nation(filter_value.value)
        else:
            filter_type = str(filter_value.value)
    
    
    if field:
        return await RandomAPI.field(
            user_id,
            filter_type,
            field,
            include_old
        )
    else:
        return await RandomAPI.overall(
            user_id,
            filter_type,
            ship_tier.value if ship_tier is not None else None,
            ship_type.value if ship_type is not None else None,
            ship_nation.value if ship_nation is not None else None,
            include_old
        )

@router.get("/users/{user_id}/ranked/overall/", summary="获取用户排位战斗总体数据")
async def getRankedOverall(
    user_id: int = Path(..., description="用户ID"),
    include_old: Optional[bool] = Query(None, description="是否包含旧船数据")
):
    """获取用户排位战斗总体数据
    
    --- 

    **权限要求**: `Root` / `User` **开发模式**: ✅ **维护模式**: ❌
    """
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if BlacklistManager.is_user_blocked(user_id):
        return JSONResponse.API_UseInBlacklist
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    if include_old is None:
        include_old = True

    return await RankedAPI.overall(
        user_id,
        include_old
    )