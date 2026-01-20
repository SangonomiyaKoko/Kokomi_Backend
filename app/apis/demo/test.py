from app.loggers import ExceptionLogger


class TestAPI:
    @ExceptionLogger.handle_program_exception_async
    async def test_error_log():
        raise NotImplementedError