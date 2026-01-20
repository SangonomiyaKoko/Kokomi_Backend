from fastapi import APIRouter, Query, Path

from app.apis.statistics import StatsAPI
from app.schemas import Region, PVPField
from app.response import JSONResponse
from app.utils import GameUtils

router = APIRouter()


@router.post("/accounts/{region}/{account_id}/refresh/", summary="刷新用户基本信息的缓存")
async def getUserBasic(region: Region = Path(...), account_id: int = Path(...)):
    if GameUtils.check_aid_and_rid(region, account_id) == False:
        return JSONResponse.API_2007_IllegalAccoutID
    result = await StatsAPI.refresh_user_cache(region, account_id)
    return result

@router.get("/accounts/{region}/{account_id}/overall/", summary="获取用户总体数据")
async def getUserBasic(region: Region = Path(...), account_id: int = Path(...), field: PVPField = Query(PVPField.PVP)):
    if GameUtils.check_aid_and_rid(region, account_id) == False:
        return JSONResponse.API_2007_IllegalAccoutID
    result = await StatsAPI.get_user_pvp(region, account_id, field)
    return result