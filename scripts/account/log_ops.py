import shutil
from pathlib import Path

from shard import (
    TimeUtils, 
    StringUtils, 
    ServicesName
)

from .logger import logger
from .settings import (
    LOG_DIR,
    DATA_DIR,
    LOG_ROTATE_MAX_BYTES,
    ERROR_INDEX_MAX_LINES,
    ERROR_LOG_RETAIN_DAYS
)


# 回扫与流式读取时的块大小
_CHUNK_SIZE = 64 * 1024

def _ensure_dir(dir: Path, folder: str):
    """确保文件夹存在"""
    folder_dir = dir / folder
    folder_dir.mkdir(exist_ok=True)


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
    now_date_filename = valid_filenames[0]
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


def _find_tail_start(index_path: Path, size: int, keep: int) -> int:
    """从文件尾部回扫，返回最新 keep 行的起始偏移

    索引文件可能正被其它服务追加，因此只按换行符切分：末尾尚未写完的半行
    不计入行数。返回 0 表示有效行数未超过 keep，无需裁剪。
    """
    found = 0

    with open(index_path, 'rb') as f:
        pos = size
        while pos > 0:
            read_size = min(_CHUNK_SIZE, pos)
            pos -= read_size
            f.seek(pos)
            chunk = f.read(read_size)

            end = len(chunk)
            while end > 0:
                offset = chunk.rfind(b'\n', 0, end)
                if offset < 0:
                    break
                found += 1
                if found > keep:
                    return pos + offset + 1
                end = offset

    return 0


def _parse_error_id(line: bytes) -> str:
    """从索引行中取出错误 ID，格式与 cleanup_error_logs 保持一致"""
    try:
        return line.decode('utf-8').strip().split(',')[-1]
    except UnicodeDecodeError:
        return ''


def _collect_exceeded_ids(index_path: Path, tail_start: int) -> list[str]:
    """流式读取即将被裁掉的索引区间，收集其中的错误 ID"""
    error_ids: list[str] = []
    remaining = tail_start
    buffer = b''

    with open(index_path, 'rb') as f:
        while remaining > 0:
            chunk = f.read(min(_CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)

            lines = (buffer + chunk).split(b'\n')
            buffer = lines.pop()

            for line in lines:
                error_id = _parse_error_id(line)
                if error_id:
                    error_ids.append(error_id)

    return error_ids


def _remove_exception_files(error_ids: list[str]) -> int:
    """删除错误 ID 对应的异常详情文件，返回删除数量"""
    removed = 0

    for error_id in error_ids:
        exception_path = LOG_DIR / 'exception' / f'{error_id}.log'
        if _remove_file(exception_path):
            removed += 1

    return removed


def limit_error_index() -> None:
    """将当日错误日志索引限制在 ERROR_INDEX_MAX_LINES 行以内

    超出上限的记录连同其异常详情一并删除，只保留最新的记录。

    索引始终就地裁剪（保留尾部、写回头部再截断），不新建替换文件：换文件会
    让其它进程已打开的句柄停留在旧文件上，其后续追加的日志将随句柄关闭一起
    丢失。裁剪也紧跟在读取之后、先于删详情执行：从取样到截断之间其它服务追
    加的日志会被一并截断，这个窗口越短越好，而详情只在裁剪成功后才删。
    """
    index_path = LOG_DIR / 'error' / TimeUtils.log_retain_days(ERROR_LOG_RETAIN_DAYS)[0]

    if not index_path.is_file():
        return

    try:
        with open(index_path, 'rb') as f:
            size = f.seek(0, 2)
    except OSError:
        logger.error(f'Failed to read: {index_path.name}')
        return

    tail_start = _find_tail_start(index_path, size, ERROR_INDEX_MAX_LINES)
    if tail_start <= 0:
        return

    try:
        with open(index_path, 'rb') as f:
            f.seek(tail_start)
            tail = f.read(size - tail_start)
    except OSError:
        logger.error(f'Failed to read: {index_path.name}')
        return

    try:
        error_ids = _collect_exceeded_ids(index_path, tail_start)
    except OSError:
        logger.error(f'Failed to read: {index_path.name}')
        return

    # 裁剪紧跟读取之后，尽量缩短「取样 -> 截断」的窗口
    try:
        with open(index_path, 'r+b') as f:
            f.write(tail)
            f.truncate()
    except OSError:
        logger.error(f'Failed to trim: {index_path.name}')
        return

    # 裁剪成功后索引才不再引用这些记录，此时删详情不会出现「索引还指着、
    # 文件却已删除」的空窗；裁剪失败则提前返回，详情不白删
    removed_exception = _remove_exception_files(error_ids)

    logger.info(
        'Error index limit - Line: %s | Exception: %s',
        len(error_ids), removed_exception
    )


def rotate_service_logs() -> None:
    """将超过大小上限的服务日志转存到暂存目录并清空原文件"""
    script_dir = LOG_DIR / 'scripts'

    for name in ServicesName.to_list():
        log_path = script_dir / f'{name}.log'

        if not log_path.exists():
            with open(log_path, 'w'):
                continue

        if not log_path.is_file():
            continue
        if log_path.stat().st_size < LOG_ROTATE_MAX_BYTES:
            continue

        try:
            trash_path = DATA_DIR / 'trash' / f'{name}_{TimeUtils.log_stamp()}.log'
            with open(log_path, 'rb') as src, open(trash_path, 'wb') as dst:
                shutil.copyfileobj(src, dst)
        except OSError:
            logger.error(
                f'Failed to dump: {log_path.name}'
            )
            if trash_path is not None:
                # 清理转存失败留下的残缺文件，避免暂存目录堆积无效数据
                _remove_file(trash_path)
            continue

        try:
            log_path.write_bytes(b'')
        except OSError:
            logger.error(
                f'Failed to truncate: {log_path.name}'
            )

        logger.info('Error log rotate -> %s', trash_path)


def maintain_log_files() -> None:
    """检查、转存和清理日志文件"""
    # 效验 LOG_DIR 路径
    if not LOG_DIR.exists():
        logger.error(f'Dir not found: {LOG_DIR}')
        return
    _ensure_dir(LOG_DIR, 'error')
    _ensure_dir(LOG_DIR, 'exception')
    _ensure_dir(LOG_DIR, 'metrics')
    _ensure_dir(LOG_DIR, 'scripts')
    cleanup_error_logs()
    limit_error_index()

    # 效验 DATA_DIR 路径
    if not DATA_DIR.exists():
        logger.error(f'Dir not found: {DATA_DIR}')
        return
    _ensure_dir(DATA_DIR, 'json')
    _ensure_dir(DATA_DIR, 'local')
    _ensure_dir(DATA_DIR, 'trash')
    rotate_service_logs()
