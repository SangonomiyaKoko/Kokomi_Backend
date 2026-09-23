from pathlib import Path

from shard import TimeUtils, StringUtils

from .logger import logger
from .settings import (
    LOG_DIR,
    ERROR_LOG_RETAIN_DAYS
)


def _remove_file(path: Path) -> bool:
    """删除文件，返回是否确实删除了文件"""
    if not path.is_file():
        return False

    try:
        path.unlink()
        return True
    except OSError:
        logger.error(f'Failed to remove: {path.name}')
        return False

def cleanup_error_logs() -> None:
    """清理保留期之外的错误日志索引及其对应的错误详情文件"""
    error_dir = LOG_DIR / 'error'

    # 返回需要保留的文件名列表
    valid_filenames = TimeUtils.log_retain_days(ERROR_LOG_RETAIN_DAYS)
    removed_index = 0
    removed_exception = 0

    for index_path in error_dir.iterdir():
        if not index_path.is_file():
            continue

        # 无法按日期解析的文件不属于日志索引，直接跳过
        if not StringUtils.is_date_format(index_path.stem):
            continue
        if index_path.name in valid_filenames:
            continue

        error_ids: list[str] = []
        try:
            with open(index_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line:
                        error_ids.append(line.split(',')[-1])
        except OSError:
            logger.error(
                f'Failed to read: {index_path.name}'
            )
            continue

        if _remove_file(index_path):
            removed_index += 1

        for error_id in error_ids:
            exception_path = LOG_DIR / 'exception' / f'{error_id}.log'
            if _remove_file(exception_path):
                removed_exception += 1

    if removed_index or removed_exception:
        logger.info(
            'Error log removed - Index: %s | Exception: %s',
            removed_index, removed_exception
        )

def maintain_log_files() -> None:
    """清理保留期之外的错误日志"""
    # 效验 LOG_DIR 路径
    if not LOG_DIR.exists():
        logger.error(f'Dir not found: {LOG_DIR}')
        return
    try:
        cleanup_error_logs()
    except Exception as e:
        logger.error(f'Clean up failed: {type(e).__name__}')
        return
