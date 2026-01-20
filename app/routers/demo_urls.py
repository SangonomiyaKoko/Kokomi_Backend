from fastapi import APIRouter, Query, Path
from typing import Optional

from app.apis.demo import UserAPI, TestAPI
from app.schemas import Region, Platform
from app.response import JSONResponse
from app.utils import GameUtils

router = APIRouter()


@router.get("/accounts/{region}/{account_id}/db/", summary="获取用户数据库中的基本信息")
async def getUserBasic(region: Region = Path(...), account_id: int = Path(...)):
    if GameUtils.check_aid_and_rid(region, account_id) == False:
        return JSONResponse.API_2007_IllegalAccoutID
    result = await UserAPI.get_user_db_info(region, account_id)
    return result

@router.get("/brief/uid/", summary="通过uid获取用户基本信息")
async def getBriefByUID(region: Region = Query(Region.ASIA), uid: int = Query(...)):
    if GameUtils.check_aid_and_rid(region, uid) == False:
        return JSONResponse.API_2007_IllegalAccoutID
    return await UserAPI.get_base(region, uid)

@router.get("/permium/status/", summary="查看用户的premium信息")
async def getPermiumStatus(platform: Platform = Query(Platform.QQ_BOT), user_id: str = Query(...)):
    return await UserAPI.get_user_premium_status(platform, user_id)

@router.get("/test/error/", summary="测试错误日志功能")
async def testErrorLog():
    return await TestAPI.test_error_log()

@router.get("/generate/code/", summary="生成激活码")
async def generateCode(
    max_use: int = Query(1),
    validity: int = Query(30),
    level: int = Query(1),
    limit: int = Query(300),
    describe: Optional[str] = None
):
    return await UserAPI.generate_code(
        max_use,
        validity,
        level,
        limit,
        describe
    )

