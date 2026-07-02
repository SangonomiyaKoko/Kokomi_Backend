from fastapi import HTTPException
from fastapi import APIRouter, Path, Query
from fastapi.responses import FileResponse

from app.core import EnvConfig, AppState
from app.utils import GameUtils
from app.middlewares import BlacklistManager
from app.response import JSONResponse
from app.apis.external import (
    ShipStatsExternalAPI,
    ShipRankingExternalAPI,
    ClanRankingExternalAPI
)


router = APIRouter(prefix="/external")

@router.get("/ship/ranking/{ship_id}/", summary="获取指定页的船只排行榜数据")
async def getShipRanking(
    ship_id: int = Path(..., description="船只 ID"),
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(50, ge=50, le=100, description="每页条数，只能选 50 或 100"),
    dogtag: int = Query(1, ge=0, le=1, description="是否在返回数据中展示用户的dogtag数据")
):
    """船只排行榜上榜条件：
    1. 船只等级大于5级
    2. 船只统计到一定场次的数据
    3. 用户未被平台拉黑

    如果某个船只不符合条件或者没有该页下的排行榜数据则返回的 data 为空 List[]

    level -> color：指标 1-8 分别对应还需努力-神佬平均这八个评级（0表示水平未知，但是理论上不应该出现）
    
    ⚠️ 关于隐藏战绩用户的特别说明：

    某个用户隐藏战绩，系统默认不会删除缓存中的数据，因此依然会参加统计

    ---

    该接口返回值 Code 含义说明（HTTP 200）:
    - 1000: 正常获取数据
    - 1001: 当前节点服务器处于维护状态
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    # 检查应用状态
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if size not in (50, 100):
        raise HTTPException(status_code=422, detail="Page size must be 50 or 100")
    
    return await ShipRankingExternalAPI.get_ship_ranking(ship_id, page, size, dogtag)


@router.get("/clan/ranking/", summary="获取指定页的船只排行榜数据")
async def getClanRanking(
    page: int = Query(1, ge=1, description="页码，从 1 开始"),
    size: int = Query(50, ge=50, le=100, description="每页条数，只能选 50 或 100")
):
    """返回工会当前赛季的排行榜

    ---

    该接口返回值 Code 含义说明（HTTP 200）:
    - 1000: 正常获取数据
    - 1001: 当前节点服务器处于维护状态
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    # 检查应用状态
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if size not in (50, 100):
        raise HTTPException(status_code=422, detail="Page size must be 50 or 100")
    
    return await ClanRankingExternalAPI.get_clan_ranking(page, size)

@router.patch("/user/refresh/{user_id}/", summary="手动触发刷新用户的缓存数据")
async def refreshUserBasic(user_id: int = Path(...)):
    """排行榜系统基于用户在本地的缓存数据进行计算，因此和最新数据存在不同步情况，如需立即更新可以通过此接口手动触发
    
    该指令会调用接口更新用户的基本信息（名称，工会，徽章等），同时将该用户标记为缓存待刷新状态，每隔 10 分钟刷新一次，并同步更新排行榜数据

    ---

    该接口返回值 Code 含义说明（HTTP 200）:
    - 1000: 该用户数据刷新成功（⚠️ 返回的 data 中不携带任何数据）
    - 1001: 当前节点服务器处于维护状态
    - 1003: 该用户 ID 下的数据不存在（404 NOT FOUND）
    - 1005: 用户数据为空，无可刷新数据
    - 1007: 用户在平台黑名单列表中（极低概率触发）
    - 1009: 用户隐藏战绩，无法刷新
    - 1010: 写入用户数据时获取分布式锁失败（极低概率触发）
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    # 检查应用状态
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if BlacklistManager.is_user_blocked(user_id):
        return JSONResponse.API_UseInBlacklist
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await ShipRankingExternalAPI.refresh_user(user_id)

@router.get("/ship/stats/", summary="获取当前服务器下船只的数据")
async def getShipStats():
    """该数据为船只的场次平均数据（非用户平均数据），仅返回有数据的船只

    ---

    该接口返回值 Code 含义说明（HTTP 200）:
    - 1000: 正常获取数据
    - 1001: 当前节点服务器处于维护状态
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    # 检查应用状态
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    return await ShipStatsExternalAPI.get_ship_stats()

@router.get("/ship/download/top50-cache/", summary="下载排行榜数据文件")
async def download_ship_ranking_msgpack():
    """获取船只排行榜中所有船只的 TOP50 缓存数据文件"""
    file_path = EnvConfig.DATA_DIR / f'trash/ship_ranking.msgpack'
    
    # 检查文件是否存在
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File ship_ranking.msgpack does not exist"
        )
    
    # 返回文件作为下载响应
    return FileResponse(
        path=file_path,
        filename="ship_ranking.msgpack",
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=ship_ranking.msgpack"
        }
    )

@router.get("/clan/download/top50-cache/", summary="下载排行榜数据文件")
async def download_clan_ranking_msgpack():
    """获取船只排行榜中所有船只的 TOP50 缓存数据文件"""
    file_path = EnvConfig.DATA_DIR / f'trash/clan_ranking.msgpack'
    
    # 检查文件是否存在
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail="File clan_ranking.msgpack does not exist"
        )
    
    # 返回文件作为下载响应
    return FileResponse(
        path=file_path,
        filename="clan_ranking.msgpack",
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=clan_ranking.msgpack"
        }
    )