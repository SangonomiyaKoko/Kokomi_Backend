from app.loggers import ExceptionLogger
from app.models import PlatformModel


class MySQLAPI:
    @ExceptionLogger.handle_program_exception_async
    async def get_innodb_trx():
        result = await PlatformModel.get_innodb_trx()
        return result

    @ExceptionLogger.handle_program_exception_async
    async def get_innodb_processlist():
        result = await PlatformModel.get_innodb_processlist()
        return result

    @ExceptionLogger.handle_program_exception_async
    async def get_basic_user_overview():
        result = await PlatformModel.get_basic_user_overview()
        return result

    @ExceptionLogger.handle_program_exception_async
    async def get_basic_clan_overview():
        result = await PlatformModel.get_basic_clan_overview()
        return result