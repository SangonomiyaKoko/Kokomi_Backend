import sys
import psutil
from fastapi import APIRouter, HTTPException, Query, Path
from fastapi.responses import FileResponse

from app.core import EnvConfig
from app.response import JSONResponse
from app.schemas import RankingFileType, VisitorToken
from app.utils import GameUtils
from app.apis.manager import (
    StateAPI, 
    MaintenanceAPI, 
    VisitorManagerAPI,
    BlacklistManagerAPI
)


router = APIRouter(prefix="/maintenance")

@router.get("/state/", summary="获取应用当前状态")
async def get_app_state():
    """获取应用当前状态
    
    返回当前APP应用的全局状态（是否处于维护模式）。
    
    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    return await StateAPI.get_node_state()

@router.put("/state/", summary="设置应用可用状态")
async def set_app_state(available: bool = Query(..., description="修改应用当前状态")):
    """修改应用当前状态
    
    设置APP应用的全局状态（维护模式），True 或 False。
    
    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    return await StateAPI.set_node_state(available)

@router.get("/system/", summary="系统的基本信息")
async def system_stats():
    """系统的基本信息
    
    返回系统的CPU和内存的实时占用信息以及硬盘使用量。
    
    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ✅ **维护模式**: ✅
    """
    is_linux = sys.platform.startswith('linux')
    return {
        "cpu": psutil.cpu_percent(interval=0.2),
        "mem": psutil.virtual_memory().percent,
        "disk": psutil.disk_usage('/').percent if is_linux else None
    }

@router.post("/visitor/token/", summary="新增访客")
async def add_visitor(token: VisitorToken):
    """新增访客
    
    增加允许访问 External 接口的 Token（Visitor权限）。
    
    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    return await VisitorManagerAPI.add_visitor(token.token, token.remark)

@router.delete("/visitor/token/{token}/", summary="删除访客")
async def del_visitor(
    token: str = Path(..., description="访客Token")
):
    """删除访客
    
    删除指定 External 接口的 Token。
    
    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    # 检查应用状态
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    return await VisitorManagerAPI.del_visitor(token)

@router.delete("/clear/user/{user_id}/", summary="清除用户数据")
async def clear_user(
    user_id: int = Path(..., description="用户ID")
):
    """清除用户数据

    完全清除用户储存在本平台内的统计数据。

    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")

    return await BlacklistManagerAPI.clear_user(user_id)

@router.post("/block/user/{user_id}/", summary="平台拉黑用户")
async def bloack_user(
    user_id: int = Path(..., description="用户ID")
):
    """平台拉黑用户
    
    列入黑名单的用户ID请求数据时会被中间件拦截，所有接口均不提供服务。

    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")

    return await BlacklistManagerAPI.block_user(user_id)

@router.post("/block/clan/{clan_id}/", summary="平台拉黑工会")
async def block_clan(
    clan_id: int = Path(..., description="工会ID")
):
    """平台拉黑工会

    列入黑名单的工会ID和工会内所有用户ID请求数据时会被中间件拦截，所有接口均不提供服务

    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    # 检查应用状态
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    if GameUtils.check_uid(clan_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")

    return await BlacklistManagerAPI.block_clan(clan_id)

@router.get("/database/meta/", summary="数据库统计指标")
async def get_database_meta():
    """数据库统计指标
    
    返回数据库的基本指标、最新游戏版本和今日错误数。

    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    return await MaintenanceAPI.get_database_meta()

@router.get("/ship/stats/", summary="船只服务器数据")
async def getShipStats():
    """船只服务器数据
    
    返回最新的船只服务器场均数据。

    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable

    return await MaintenanceAPI.get_ship_stats()

@router.post("/ship/refresh/", summary="刷新船只基础数据表")
async def refreshShipBase(ships: dict):
    """刷新船只基础数据表
    
    通过请求携带的 JSON 数据刷新 T_ship_base 及相关表。
    
    JSON 格式为：
    ```
    {
        ship_id: [is_old, tier, type_id, nation_id, rarity_id, premium, special, index_code, ship_name], 
        ... 
    }
    ```

    --- 

    **权限要求**: `Root` / `Manager` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    # 数据效验
    if not ships or not isinstance(ships, dict):
        raise HTTPException(status_code=422, detail="Invalid payload")
    
    for ship_id, ship_data in ships.items():
        # 校验key是否为数字字符串
        if not isinstance(ship_id, str) or not ship_id.isdigit():
            raise HTTPException(status_code=422, detail="Invalid payload")
        
        # 校验value是否为列表且长度为9
        if not isinstance(ship_data, list) or len(ship_data) != 9:
            raise HTTPException(status_code=422, detail="Invalid payload")

    return await MaintenanceAPI.refresh_ship_base(ships)

@router.get("/ranking/download/", summary="下载排行榜数据文件")
async def download_ranking_msgpack(
    file_type: RankingFileType = Query(RankingFileType.SHIP_RANKING,description="文件类型")
):
    """下载排行榜数据文件
    
    文件格式为经过 MessagePack 序列化的JSON文件，直接反序列化即可提取数据。

    反序列化的 JSON 文件格式：
    ```
    {
        'time': refresh_timestamp,    # 文件更新的时间戳
        'data': {
            'ship_id': payload(Dict)  # 负载数据（Dict）
        }
    }
    ```

    Payload 数据格式
    ```
    {
        'limit': 0,    # 该船只的最低战斗场次要求
        'users': 0,    # 该船只上榜用户总数
        'rows': rows(List)   # 该船只的 TOP50 缓存数据（List）
    }
    ```

    Rows 数据格式
    ```
    [
        rank, user_id, clan_tag, league, username, battles, rating, 
        win_rate, win_rate_level, avg_damage, avg_damage_level, avg_frags, 
        avg_frags_level, avg_exp, hit_ratio, max_exp, max_damage
    ]
    ```
    
    --- 

    **权限要求**: `Root` / `Visitor` **开发模式**: ✅ **维护模式**: ✅
    """
    file_path = EnvConfig.DATA_DIR / f'trash/{file_type.value}.msgpack'
    
    # 检查文件是否存在
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"File {file_type.value}.msgpack does not exist"
        )
    
    # 返回文件作为下载响应
    return FileResponse(
        path=file_path,
        filename=f"{file_type.value}.msgpack",
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename={file_type.value}.msgpack"
        }
    )