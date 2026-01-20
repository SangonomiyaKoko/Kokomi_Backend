from typing import Literal
from fastapi import APIRouter, Query

from app.apis.platform import RefreshAPI, MySQLAPI, UpdateAPI
from app.schemas import Server, Region

router = APIRouter()

@router.put("/refresh/vehicles/", summary="刷新船只数据")
async def searchUser(server: Server = Query(Server.WG)):
    return await RefreshAPI.refreshVehicles(server)

@router.put("/refresh/config/", summary="刷新配置参数")
async def searchUser():
    return await RefreshAPI.refreshConfig()

@router.put("/refresh/game-version/", summary="获取并更新游戏当前版本号")
async def updateGameVersion(region: Region = Query(Region.ASIA)):
    return await UpdateAPI.updateGameVersion(region)


@router.get("/mysql/overview/", summary="获取数据库概览")
async def getMySQLOverview(item: Literal['user', 'clan', 'trx', 'process']):
    if item == 'user':
        result = await MySQLAPI.get_basic_user_overview()
    elif item == 'clan':
        result = await MySQLAPI.get_basic_clan_overview()
    elif item == 'trx':
        result = await MySQLAPI.get_innodb_trx()
    else:
        result = await MySQLAPI.get_innodb_processlist()
    return result