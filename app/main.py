#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import threading
from fastapi import FastAPI, Request, Security
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
from starlette.responses import StreamingResponse

from app.response import JSONResponse
from app.core import EnvConfig, AppState, api_logger
from app.utils import TimeUtils
from app.loggers import CSVWriter, log_queue
from app.database import MySQLManager
from app.network import HttpClient
from app.utils import RatingUtils
from app.middlewares import (
    RedisConnection,
    SecurityManager, 
    ServiceMetrics,
    VisitorManager,
    BlacklistManager
)
from app.dashboard import dashboard_router
from app.routers import (
    platform_router, 
    demo_router, 
    statistics_router,
    recent_router,
    ranking_router,
    miantenance_router,
    external_router
)


# 后台日志写入线程，用于将日志队列中的请求信息写入CSV文件
def csv_writer_thread():
    writer = CSVWriter()
    api_logger.info('The log writing thread has been started')
    while True:
        record = log_queue.get()
        api_logger.debug('Received a log data to be written')
        if record is None:  # 退出信号
            break
        writer.write(record)
        log_queue.task_done()

    writer.close()
    api_logger.info('The log writing thread has exited')

async def app_init():
    # 初始化http客户端
    HttpClient.init_client()
    # 初始化mysql并测试mysql连接
    await MySQLManager.init_pool()
    await MySQLManager.test_connection()
    # 初始化并测试redis连接
    await RedisConnection.init_conn()
    await RedisConnection.test_redis()
    # 初始化全局状态
    app_state = await RedisConnection.load_state()
    AppState.init(app_state)
    api_logger.info(f'API available: {app_state}')
    # 加载访客令牌管理器
    VisitorManager.init()
    # 初始化黑名单管理器
    BlacklistManager.init()
    # 加载工具函数所需的全局配置数据
    RatingUtils.init(EnvConfig.get_constants().METRIC_RATING_THRESHOLDS)

# 应用程序的生命周期管理
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 读取工作路径，加载配置文件
    ROOT_DIR = os.getcwd()
    api_logger.info(f'Working dir: {ROOT_DIR}')
    # 从环境中加载配置
    env_file = EnvConfig.init(ROOT_DIR)
    if env_file:
        api_logger.info(f"Env config loaded: {env_file}")
    else:
        api_logger.error("Env config load failed")
    api_logger.info(f"Current region: {EnvConfig.REGION.upper()}")

    # 启动API日志写入线程
    writer_thread = threading.Thread(target=csv_writer_thread, daemon=True)
    writer_thread.start()
    
    # 应用初始化
    await app_init()

    # 启动 lifespan
    try:
        yield
    finally:
        await HttpClient.close_client()
        await MySQLManager.close_pool()
        await RedisConnection.close_redis()
        # 发送退出信号，等待剩下数据写入并退出线程
        log_queue.put(None)
        writer_thread.join()

app_description = """
接口返回值文档：https://github.com/SangonomiyaKoko/Kokomi_Backend/blob/main/docs/return.md
"""

# 加载APP
app = FastAPI(
    lifespan=lifespan,
    description=app_description
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory="app/static"), name="static")


# 请求中间件
@app.middleware("http")
async def request_rate_limiter(request: Request, call_next):
    # 由于子节点接口仅限授权用户访问，目前不需要考虑IP黑名单问题
    # client_ip = request.client.host if request.client else None
    # if client_ip != '127.0.0.1':
    #     return JSONResponse(
    #         status_code=403,
    #         content={"detail": "Forbidden"}
    #     )
    start = TimeUtils.timestamp_ms()
    now_time = TimeUtils.now_iso()
    try:
        await ServiceMetrics.api_incr(now_time[0:10])
    except Exception:
        pass
    response: StreamingResponse = await call_next(request)
    elapsed = int((TimeUtils.timestamp_ms() - start))
    record = [
        now_time,
        request.client.host if request.client else "-",
        request.method,
        request.url,
        response.status_code,
        elapsed
    ]
    try:
        log_queue.put_nowait(record)
    except Exception:
        api_logger.warning('Log queue full')
        pass  # 队列满时直接丢弃，避免阻塞接口
    return response


# 测试接口
@app.get("/", summary='Home', tags=['Default'])
async def root():
    """
    测试接口连通性
    """
    return JSONResponse.API_1000_Success

@app.get("/permission/", summary="测试当前token是否可用", tags=['Default'])
async def testRootPermission(role: bool = Security(SecurityManager.get_current_role)):
    return JSONResponse.success(role)

@app.get("/dashboard")
async def redirect():
    """重定向到看板首页"""
    return RedirectResponse(url="/dashboard/overview")

# 在主路由中注册子路由
app.include_router(
    dashboard_router, 
    prefix="/dashboard", 
    tags=['Dashboard']
)

app.include_router(
    demo_router, 
    prefix='/api',
    tags=['Demo Interface'],
    dependencies=[Security(SecurityManager.require_root)]
)

app.include_router(
    miantenance_router, 
    prefix='/api',
    tags=['Miantenance Interface'],
    dependencies=[Security(SecurityManager.require_manager)]
)

app.include_router(
    external_router, 
    prefix='/api',
    tags=['External Interface'],
    dependencies=[Security(SecurityManager.require_vistor)]
)

app.include_router(
    platform_router, 
    prefix='/api',
    tags=['Platform Interface'],
    dependencies=[Security(SecurityManager.require_user)]
)

app.include_router(
    ranking_router,
    prefix='/api',
    tags=['Ranking Interface'],
    dependencies=[Security(SecurityManager.require_user)]
)

app.include_router(
    statistics_router,
    prefix="/api",
    tags=['Statistics Interface'],
    dependencies=[Security(SecurityManager.require_user)]
)

app.include_router(
    recent_router,
    prefix="/api",
    tags=['Recent Interface'],
    dependencies=[Security(SecurityManager.require_user)]
)

# 重写 shutdown 函数，避免某些协程在关闭时出错
# async def _shutdown(self, any = None):
#     await origin_shutdown(self)
#     wait_second = 1
#     while wait_second > 0:
#         api_logger.info(f'App will close after {wait_second} seconds')
#         await asyncio.sleep(1)
#         wait_second -= 1
#     api_logger.info('App has been closed')

# origin_shutdown = asyncio.BaseEventLoop.shutdown_default_executor
# asyncio.BaseEventLoop.shutdown_default_executor = _shutdown