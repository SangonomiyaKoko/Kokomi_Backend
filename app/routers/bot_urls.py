from fastapi import APIRouter, Query, Path

from app.response import JSONResponse
from app.apis.statistics import SearchAPI
from app.apis.robot import BindAPI, TokenAPI
from app.schemas import Region, Language, ShipFilter, Platform, BindBody, BindIndex
from app.utils import GameUtils, StringUtils

router = APIRouter()

@router.get("/search/user/", summary="搜索用户")
async def searchUser(region: Region = Query(Region.ASIA), content: str = Query(...), limit: int = 1):
    if not 3 <= len(content) <= 25:
        return JSONResponse.API_2002_IllegalUserName
    return await SearchAPI.search_user(region, content, limit)

@router.get("/search/clan/", summary="搜索工会")
async def searchClan(region: Region = Query(Region.ASIA), content: str = Query(...), limit: int = 1):
    if not 3 <= len(content) <= 5:
        return JSONResponse.API_2003_IllegalClanTag
    return await SearchAPI.search_clan(region, content, limit)

@router.get("/search/ship/", summary="搜索船只")
async def searchShip(region: Region = Query(Region.ASIA), content: str = Query(...), language: Language = Query(Language.CN)):
    if not 2 <= len(content) <= 25:
        return JSONResponse.API_2004_IllegalShipName
    return await SearchAPI.search_ship(region, content, language)

@router.post("/query/ship/", summary="查询船只")
async def queryShip(region: Region, query_condition: ShipFilter):
    return await SearchAPI.query_ship(region, query_condition)

@router.delete("/accounts/{account_id}/ac/", summary="删除ac")
async def setAC(account_id: int = Path(...)):
    return await TokenAPI.del_ac(account_id)

@router.delete("/accounts/{account_id}/auth/", summary="删除auth")
async def setAC(account_id: int = Path(...)):
    return await TokenAPI.del_auth(account_id)

@router.post("/users/{platform}/{user_id}/bindings/", summary="通过uid/ign绑定")
async def getBind(body: BindBody, platform: Platform = Path(...), user_id: str = Path(...)):
    if body.type == 'ign':
        if not 3 <= len(body.ign) <= 25:
            return JSONResponse.API_2002_IllegalUserName
    else:
        if GameUtils.check_aid_and_rid(body.region, body.uid) == False:
            return JSONResponse.API_2007_IllegalAccoutID
    return await BindAPI.postBind(platform, user_id, body)

@router.get("/users/{platform}/{user_id}/accounts/", summary="查询绑定数据")
async def getBind(platform: Platform = Path(...), user_id: str = Path(...)):
    return await BindAPI.getBind(platform, user_id)

@router.get("/users/{platform}/{user_id}/accounts/list/", summary="查询绑定列表数据")
async def getBind(platform: Platform = Path(...), user_id: str = Path(...)):
    return await BindAPI.getBindList(platform, user_id)

@router.delete("/users/{platform}/{user_id}/accounts/", summary="删除指定绑定")
async def delBind(platform: Platform = Path(...), user_id: str = Path(...), index: BindIndex = Query(BindIndex.IDX1)):
    return await BindAPI.delBind(platform, user_id, index)

@router.patch("/users/{platform}/{user_id}/accounts/", summary="切换绑定")
async def switchBind(platform: Platform = Path(...), user_id: str = Path(...), index: BindIndex = Query(BindIndex.IDX1)):
    return await BindAPI.switchBind(platform, user_id, index)

@router.post("/users/{platform}/{user_id}/premium/", summary="使用激活码")
async def activateCode(platform: Platform = Path(...), user_id: str = Path(...), code: str = Query(...)):
    if StringUtils.is_valid_activation_code(code) is False:
        return JSONResponse.API_2023_InvalidActivationCode
    return await BindAPI.activateCode(platform,user_id,code)