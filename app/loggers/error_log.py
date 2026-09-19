from typing import Optional

from shard import exception_writer

from app.core import EnvConfig


def write_exception(
    error_type: str,
    error_name: str,
    error_info: Optional[str] = None,
    error_id: Optional[str] = None
) -> str:
    """写入异常摘要和详细异常日志，返回本次异常的 ID"""
    return exception_writer(
        log_dir=EnvConfig.LOG_DIR,
        client_id='API',
        error_type=error_type,
        error_name=error_name,
        error_info=error_info,
        error_id=error_id
    )
