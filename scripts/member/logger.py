import sys
from typing import Optional

from shard import (
    ServicesName,
    create_logger,
    exception_writer
)

from .settings import (
    LOG_DIR,
    LOG_LEVEL
)


def write_exception(
    error_type: str,
    error_name: str,
    error_info: Optional[str] = None,
    error_id: Optional[str] = None
) -> str:
    """写入异常摘要和详细异常日志，返回本次异常的 ID"""
    return exception_writer(
        log_dir=LOG_DIR,
        client_id=ServicesName.MEMBER,
        error_type=error_type,
        error_name=error_name,
        error_info=error_info,
        error_id=error_id
    )


logger = create_logger(
    name=ServicesName.MEMBER,
    log_dir=LOG_DIR,
    level=LOG_LEVEL,
    use_tqdm=sys.stdout.isatty()
)
