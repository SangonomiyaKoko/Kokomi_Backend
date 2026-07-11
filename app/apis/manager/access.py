from app.loggers import ExceptionLogger
from app.middlewares import VisitorManager
from app.response import JSONResponse, ResponseDict


class VisitorManagerAPI:
    @ExceptionLogger.handle_program_exception_async
    async def get_all_visitors() -> ResponseDict:
        result = VisitorManager.get_all()
        return JSONResponse.success(result)

    @ExceptionLogger.handle_program_exception_async
    async def add_visitor(token: str, remark: str = None) -> ResponseDict:
        result = VisitorManager.add(token, remark)
        return JSONResponse.success(result)

    @ExceptionLogger.handle_program_exception_async
    async def del_visitor(token: str) -> ResponseDict:
        VisitorManager.delete(token)
        return JSONResponse.API_1000_Success