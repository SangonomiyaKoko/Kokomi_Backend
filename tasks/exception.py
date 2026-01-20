import os
import uuid
import traceback
from datetime import datetime, timezone


LOG_DIR = '/app/logs'
ERROR_LOG_PATH = os.path.join(LOG_DIR, "error")

def write_error_info(
    error_id: str,
    error_type: str,
    error_name: str,
    error_args: str = None,
    error_info: str = None
):
    form_time = datetime.now(timezone.utc).isoformat()
    with open(os.path.join(ERROR_LOG_PATH, f'{form_time[0:10]}.txt'), "a", encoding="utf-8") as f:
        f.write('-------------------------------------------------------------------------------------------------------------\n')
        f.write(f">Platform:     Celery\n")
        f.write(f">Error ID:     {error_id}\n")
        f.write(f">Error Type:   {error_type}\n")
        f.write(f">Error Name:   {error_name}\n")
        f.write(f">Error Time:   {form_time}\n")
        f.write(f">Error Info:   \n{error_args}\n{error_info}\n")
        f.write('-------------------------------------------------------------------------------------------------------------\n')
    f.close()


def handle_program_exception_sync(func):
    "负责异步程序异常信息的捕获"
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            return result
        except Exception as e:
            write_error_info(
                error_id = str(uuid.uuid4()),
                error_type = 'ProgramError',
                error_name = str(type(e).__name__),
                error_args = str(args) + str(kwargs),
                error_info = traceback.format_exc()
            )
            return 'program error'
    return wrapper
    