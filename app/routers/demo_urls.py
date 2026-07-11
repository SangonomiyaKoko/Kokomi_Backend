from typing import Literal
from fastapi import HTTPException, APIRouter, Query, Path

from app.core import EnvConfig, AppState
from app.response import JSONResponse
from app.utils import GameUtils
from app.schemas import RecentLevel

from app.apis.manager import VisitorManagerAPI
from app.apis.demo import (
    TestAPI, MySQLAPI
)

router = APIRouter(prefix="/demo")


ALLOWED_TRACKING_KEYS = Literal['table_meta', 'ship_stats', 'clan_season']


@router.get("/raise_error/", summary="测试异常捕获机制")
async def test_error_log ():
    """测试异常捕获机制
    
    测试平台的系统错误捕获机制，生成错误日志文件并返回错误响应。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    return await TestAPI.test_error_log()


@router.delete("/error_logs/", summary="删除所有错误日志")
async def delete_error_logs():
    """删除所有错误日志
    
    遍历删除所有错误日志文件和索引文件，返回删除的日志数量。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    return await TestAPI.delete_error_logs()


@router.delete("/service_logs/", summary="清空所有服务的异常日志数据")
async def clear_service_logs():
    """清空所有服务的异常日志数据
    
    清理子服务运行中产生的异常日志数据，返回清空的文件数量。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    return await TestAPI.clear_service_logs()


@router.post("/tracking/reset/", summary="重置指定服务追踪的更新时间")
async def reset_tracking_time(
    key: ALLOWED_TRACKING_KEYS = Query(..., description="追踪服务的 Key")
):
    """重置指定服务追踪的更新时间

    将表中 tracking_value 置为 NULL，强制服务在下个更新轮次里触发刷新。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ❌
    """
    # 检查应用状态
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    return await MySQLAPI.reset_tracking_time(key)

@router.get("/visitor/token/", summary="获取已加载的访客 Token")
async def get_all_token():
    """获取已加载的访客 Token
    
    从内存中读取并返回所有已加载访客 Token 和 Remark 信息。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    return await VisitorManagerAPI.get_all_visitors()


@router.get("/user/{user_id}/db/", summary="获取用户数据库中的基本信息")
async def get_user_db(
    user_id: int = Path(..., description="用户ID")
):
    """获取用户数据库中的基本信息
    
    从数据库读取用户的基本信息，用于检测和DEBUG。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if not GameUtils.check_uid(user_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await MySQLAPI.get_user_overview(user_id)


@router.delete("/user/{user_id}/db/", summary="关闭指定用户的更新计划")
async def del_user_db(
    user_id: int = Path(..., description="用户ID")
):
    """关闭指定用户的更新计划
    
    将用户ID标记为不可用并清理缓存待更新标记，仅用于测试。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if not GameUtils.check_uid(user_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await MySQLAPI.set_user_status(user_id, 0)


@router.patch("/user/{user_id}/db/", summary="恢复指定用户的更新计划")
async def patch_user_db(
    user_id: int = Path(..., description="用户ID")
):
    """恢复指定用户的更新计划
    
    将用户ID标记为可用，仅用于测试。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if not GameUtils.check_uid(user_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await MySQLAPI.set_user_status(user_id, 1)


@router.get("/clan/{clan_id}/db/", summary="获取工会数据库中的基本信息")
async def get_clan_db(
    clan_id: int = Path(..., description="工会ID")
):
    """获取工会数据库中的基本信息
    
    从数据库读取工会的基本信息，用于检测和DEBUG。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if not GameUtils.check_uid(clan_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await MySQLAPI.get_clan_overview(clan_id)


@router.delete("/clan/{clan_id}/db/", summary="关闭指定工会的更新计划")
async def del_clan_db(
    clan_id: int = Path(..., description="工会ID")
):
    """关闭指定工会的更新计划
    
    将工会ID标记为不可用，仅用于测试。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if not GameUtils.check_uid(clan_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await MySQLAPI.set_clan_status(clan_id, 0)


@router.patch("/clan/{clan_id}/db/", summary="恢复指定工会的更新计划")
async def patch_clan_db(
    clan_id: int = Path(..., description="工会ID")
):
    """恢复指定工会的更新计划
    
    将工会ID标记为可用，仅用于测试。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ❌
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    if not AppState.is_available():
        return JSONResponse.API_NodeNotAvailable
    
    if not GameUtils.check_uid(clan_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await MySQLAPI.set_clan_status(clan_id, 1)


@router.get("/clan-battle/{season_id}/db/", summary="获取赛季工会战数据库的基本信息")
async def get_clan_db(
    season_id: int = Path(..., ge=1, le=50, description="赛季ID")
):
    """获取赛季工会战数据库的基本信息
    
    返回指定赛季ID统计到的战斗记录条数，用于检测和DEBUG。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    return await MySQLAPI.get_clan_season_overview(season_id)


@router.get("/blacklist/list/", summary="平台黑名单列表")
async def block_user():
    """平台黑名单列表
    
    返回当前加载的平台黑名单列表。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    return await TestAPI.get_all_blacklist()


@router.delete("/block/user/{user_id}/", summary="从平台黑名单中移除用户")
async def block_user(
    user_id: int = Path(..., description="用户ID")
):
    """从平台黑名单中移除用户
    
    将用户ID从平台黑名单中移除，仅 Root 权限可操作。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    if GameUtils.check_uid(user_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")

    return await TestAPI.remove_user(user_id)


@router.delete("/block/clan/{clan_id}/", summary="从平台黑名单中移除工会")
async def block_clan(
    clan_id: int = Path(..., description="工会ID")
):
    """从平台黑名单中移除工会
    
    将工会ID从平台黑名单中移除，仅 Root 权限可操作。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    
    if GameUtils.check_uid(clan_id) == False:
        raise HTTPException(status_code=422, detail="Invalid UID")

    return await TestAPI.remove_clan(clan_id)


@router.get("/recent/overview/", summary="船只版本近期数据概览")
async def get_recent_overview ():
    """船只版本近期数据概览
    
    返回按版本区分的版本内近期总战斗场次，用于检测和DEBUG。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    return await MySQLAPI.get_version_overview()


@router.get("/staging/overview/", summary="船只暂存表数据概览")
async def get_staging_overview():
    """船只暂存表数据概览
    
    返回当前船只近期数据暂存表内不同status的行数统计，用于检测和DEBUG。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    result = await MySQLAPI.get_staging_overview()
    return result


@router.get("/user/{user_id}/basic/", summary="获取用户最新的基本信息")
async def get_user_basic(
    user_id: int = Path(..., description="用户ID")
):
    """获取用户最新的基本信息
    
    请求游戏接口，读取最新的用户基本信息，仅读取数据不写入数据库。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    if not GameUtils.check_uid(user_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await TestAPI.get_user_basic(user_id)


@router.get("/user/{user_id}/clan/", summary="获取用户最新的工会信息")
async def get_user_clan(
    user_id: int = Path(..., description="用户ID")
):
    """获取用户最新的工会信息
    
    请求游戏接口，读取最新的用户工会信息，仅读取数据不写入数据库。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    if not GameUtils.check_uid(user_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    result = await TestAPI.get_user_clan(user_id)
    return result


@router.get("/clan/{clan_id}/basic/", summary="获取工会最新的基本信息")
async def get_clan_basic(
    clan_id: int = Path(..., description="工会ID")
):
    """获取工会最新的基本信息
    
    请求游戏接口，读取最新的工会基本信息，仅读取数据不写入数据库。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    if not GameUtils.check_uid(clan_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    result = await TestAPI.get_clan_basic(clan_id)
    return result


@router.get("/clan/{clan_id}/members/", summary="获取工会最新的会内玩家列表")
async def get_clan_members(
    clan_id: int = Path(..., description="工会ID")
):
    """获取工会最新的会内玩家列表
    
    请求游戏接口，读取最新的工会会内玩家列表，仅读取数据不写入数据库。
    
    --- 

    **权限要求**: `Root` **开发模式**: ✅ **维护模式**: ✅
    """
    if not GameUtils.check_uid(clan_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    result = await TestAPI.get_clan_members(clan_id)
    return result


@router.post("/user/{user_id}/features/enable/", summary="启用记录玩家近期数据功能")
async def enable_user_features(
    user_id: int = Path(..., description="用户ID"),
    level: RecentLevel = Query(RecentLevel.standard, description="功能等级")
):
    """启用记录玩家近期数据功能
    
    启用或升级记录玩家近期数据功能（Recent），等级仅可向上提升，返回是否操作成功。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    if not GameUtils.check_uid(user_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await TestAPI.set_recent(user_id, level.value)


@router.patch("/user/{user_id}/features/downgrade/", summary="降级用户记录近期数据功能等级")
async def downgrade_user_features(
    user_id: int = Path(..., description="用户ID")
):
    """降级用户记录近期数据功能等级
    
    将功能等级从 plus 降级为 standard，并清理数据，返回是否操作成功。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    if not GameUtils.check_uid(user_id):
        raise HTTPException(status_code=422, detail="Invalid UID")
    
    return await TestAPI.demotion_recent(user_id)

@router.delete("/user/{user_id}/features/disable/", summary="关闭用户的Recent功能")
async def disable_recent(
    user_id: int = Path(..., description="用户ID")
):
    """关闭用户的Recent功能
    
    关闭指定用户的记录近期数据功能，并清理已有数据。
    
    --- 

    **权限要求**: `Root` **开发模式**: ❌ **维护模式**: ✅
    """
    if EnvConfig.DEV_MODE:
        return JSONResponse.API_NodeNotAvailable
    
    return await TestAPI.disable_recent(user_id)