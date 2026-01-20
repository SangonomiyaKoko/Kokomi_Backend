import uuid
import httpx
import traceback

from .response import JSONResponse
from app.loggers import write_error_info

def handle_network_exception_async(func):
    "负责异步网络请求 httpx 的异常捕获"
    async def wrapper(*args, **kwargs):
        try:
            result = await func(*args, **kwargs)
            return result
        except httpx.ConnectTimeout:
            return JSONResponse.get_error_response(5001,'HttpxConnectTimeout')
        except httpx.ReadTimeout:
            return JSONResponse.get_error_response(5002,'HttpxReadTimeout')
        except httpx.TimeoutException:
            return JSONResponse.get_error_response(5003,'HttpxTimeoutError')
        except httpx.ConnectError:
            return JSONResponse.get_error_response(5004,'HttpxConnectError')
        except httpx.ReadError:
            return JSONResponse.get_error_response(5005,'HttpxReadError')
        except httpx.HTTPStatusError:
            return JSONResponse.get_error_response(5006, 'HttpxHTTPStatusError')
        except Exception as e:
            error_id = str(uuid.uuid4())
            write_error_info(
                error_id = error_id,
                error_type = 'NetworkError',
                error_name = str(type(e).__name__),
                error_args = str(args) + str(kwargs),
                error_info = traceback.format_exc()
            )
            return JSONResponse.get_error_response(5000,'NetworkError',error_id)
    return wrapper

async def record_request():
    ...