from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates

from app.core import EnvConfig
from .services import (
    get_overview_data, 
    get_celery_data, 
    get_game_api_data, 
    get_database_data, 
    get_user_activity_data, 
    get_error_logs_data, 
    get_exception_detail
)


PROJECT_GITHUB_URL = "https://github.com/SangonomiyaKoko/Kokomi_Backend"

router = APIRouter()

templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


def _node_info():
    return {
        "Region": EnvConfig.REGION.upper(),
        "Timezone": f'UTC{EnvConfig.TIMEZONE:+d}',
        "Location": EnvConfig.LOCATION,
        "Init Time": EnvConfig.INIT_TIME,
    }


def _render(request: Request, template: str, active_page: str, data: dict):
    return templates.TemplateResponse(
        template,
        {
            "request": request,
            "active_page": active_page,
            "node_name": f"{EnvConfig.REGION.upper()} Node",
            "github_url": PROJECT_GITHUB_URL,
            "node_info": _node_info(),
            **data,
        },
    )


@router.get("/overview")
async def overview(request: Request):
    return _render(request, "overview.html", "overview", await get_overview_data())


@router.get("/game-api")
async def api_stats(request: Request):
    return _render(request, "game_api.html", "game-api", await get_game_api_data())


@router.get("/celery")
async def celery_stats(request: Request):
    return _render(request, "celery.html", "celery", await get_celery_data())


@router.get("/database")
async def database_stats(request: Request):
    return _render(request, "database.html", "database", await get_database_data())


@router.get("/update-plans")
async def update_plans(request: Request):
    return _render(request, "update_plans.html", "update-plans", await get_user_activity_data())


@router.get("/error-logs")
async def error_logs(
    request: Request,
    page: int = 1,
    per_page: int = 10,
):
    """错误日志列表页面"""
    from datetime import datetime, timezone

    today = datetime.now(timezone.utc).date()
    data = get_error_logs_data(today, EnvConfig.LOG_DIR, page, per_page)

    return _render(
        request,
        "error_logs.html",
        "error-logs",
        {
            "entries": data["entries"],
            "page": data["page"],
            "per_page": data["per_page"],
            "total": data["total"],
            "total_pages": data["total_pages"],
            "today": today.isoformat(),
            "api_errors": data["api_errors"],
            "celery_errors": data["celery_errors"],
            "other_errors": data["other_errors"],
        },
    )


@router.get("/exception")
async def exception_detail(request: Request, uuid: str = ""):
    """异常详情查看页面"""
    detail = None
    if uuid:
        detail = get_exception_detail(uuid, EnvConfig.LOG_DIR)

    return _render(
        request,
        "exception.html",
        "exception",
        {
            "uuid": uuid,
            "detail": detail,
        },
    )