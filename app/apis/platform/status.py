from app.loggers import ExceptionLogger
from app.utils import TimeUtils
from app.health import ServiceMetrics
from app.response import JSONResponse


class StatusAPI:
    @ExceptionLogger.handle_program_exception_async
    async def api_stats():
        """"""
        result = {
            "page": "api",
            "timezone": "UTC+8",
            "timeatamp": TimeUtils.timestamp(),
            "metrics": {}
        }
        overall = ServiceMetrics.collect_today_hourly_metrics()
        api = await ServiceMetrics.collect_api_metrics()
        celery = await ServiceMetrics.collect_celery_metrics()
        result['metrics'] ={
            "today_api": overall,
            "api_30d": api,
            "celery_30d": celery
        }
        return JSONResponse.get_success_response(result)