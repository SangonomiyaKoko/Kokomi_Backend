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
        http_count, http, error = await ServiceMetrics.collect_http_metrics()
        result['metrics'] ={
            'today': {
                'requests': overall['summary']['total_requests'],
                'errors': overall['summary']['total_errors'],
                'elapsed_ms': overall['summary']['elapsed_ms'],
                'api_counts': http_count[0],
                'failed_counts': http_count[1]
            },
            "api_request_today": overall['hourly'],
            "api_request_30d": api,
            "celery_tasks_30d": celery,
            "api_calls_14d": http,
            "api_failed_rate_14d": error
        }
        return JSONResponse.get_success_response(result)