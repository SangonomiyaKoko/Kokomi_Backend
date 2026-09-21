import sys
import uuid
import logging
from pathlib import Path
from typing import Callable, Optional, Iterator

from tqdm import tqdm

from .utils.time import TimeUtils


# 日志输出格式
LOG_FORMAT = '%(asctime)s [%(levelname)s] %(message)s'

# 日志时间格式
DATE_FMT = '%Y-%m-%d %H:%M:%S'


class TqdmAwareLogger(logging.Logger):
    """兼容 tqdm 进度条的日志器

    tqdm 进度条与 logging 默认都向 stdout 输出，二者混用会打断进度条渲染
    导致输出错行。本类在 tqdm 模式下改用 tqdm.write 输出控制台日志，从而与
    进度条共存；文件日志不受影响，仍按原级别过滤后写入。

    该类由 create_logger 内部通过 logging.setLoggerClass 安装，
    业务代码一般无需手动实例化，仅需在类型注解中引用。
    """

    def __init__(
        self,
        name: str,
        level: int = logging.DEBUG,
        use_tqdm: bool = False,
    ) -> None:
        super().__init__(name, level)
        self._tqdm_allowed = use_tqdm    # 是否允许进入 tqdm 模式
        self._use_tqdm = False           # 当前是否处于 tqdm 模式
        self._console_handler: Optional[logging.Handler] = None
        self._file_handler: Optional[logging.Handler] = None

    @property
    def use_tqdm(self) -> bool:
        return self._use_tqdm

    def set_handlers(
        self,
        console_handler: logging.Handler,
        file_handler: logging.Handler,
    ) -> None:
        """挂载控制台与文件 handler"""
        self._console_handler = console_handler
        self._file_handler = file_handler
        self.addHandler(console_handler)
        self.addHandler(file_handler)

    def set_tqdm_enabled(self, enabled: bool = True) -> None:
        """设置是否允许进入 tqdm 模式"""
        self._tqdm_allowed = enabled

    def enable_tqdm(self) -> None:
        """进入 tqdm 模式：摘除控制台 handler，避免与进度条抢占 stdout"""
        if not self._use_tqdm and self._tqdm_allowed:
            self._use_tqdm = True
            if (
                self._console_handler
                and self._console_handler in self.handlers
            ):
                self.removeHandler(self._console_handler)

    def disable_tqdm(self) -> None:
        """退出 tqdm 模式：恢复控制台 handler"""
        if self._use_tqdm:
            self._use_tqdm = False
            if (
                self._console_handler
                and self._console_handler not in self.handlers
            ):
                self.addHandler(self._console_handler)

    def _write(
        self,
        level_name: str,
        log_method: Callable[..., None],
        msg: str,
        *args: object,
        **kwargs: object,
    ) -> None:
        """统一的日志出口：tqdm 模式下走 tqdm.write，否则走 logging 原生输出"""
        if self._use_tqdm:
            self._tqdm_log(level_name, msg, *args, **kwargs)
        else:
            log_method(msg, *args, **kwargs)

    def _tqdm_log(
        self,
        level_name: str,
        msg: str,
        *args: object,
        **kwargs: object,
    ) -> None:
        """tqdm 模式下的日志输出：控制台走 tqdm.write，文件仍按级别过滤写入"""
        # 预格式化消息，tqdm.write 不做 % 占位符替换
        if args:
            try:
                msg = msg % args
            except TypeError:
                pass

        tqdm.write(f'{TimeUtils.log_time()} [{level_name}] {msg}')

        # 按文件 handler 自身的级别过滤，与普通模式下 handler 的行为保持一致
        level_value = getattr(logging, level_name, logging.WARNING)
        file_level = self._file_handler.level if self._file_handler else None
        if file_level is not None and level_value >= file_level:
            log_record = logging.LogRecord(
                name=self.name,
                level=level_value,
                pathname='',
                lineno=0,
                msg=msg,
                args=(),
                exc_info=None
            )
            self._file_handler.emit(log_record)

    def debug(self, msg: str, *args: object, **kwargs: object) -> None:
        """输出 DEBUG 日志"""
        self._write('DEBUG', super().debug, msg, *args, **kwargs)

    def info(self, msg: str, *args: object, **kwargs: object) -> None:
        """输出 INFO 日志"""
        self._write('INFO', super().info, msg, *args, **kwargs)

    def warning(self, msg: str, *args: object, **kwargs: object) -> None:
        """输出 WARNING 日志"""
        self._write('WARNING', super().warning, msg, *args, **kwargs)

    def error(self, msg: str, *args: object, **kwargs: object) -> None:
        """输出 ERROR 日志"""
        self._write('ERROR', super().error, msg, *args, **kwargs)


def _resolve_level(level: 'int | str') -> int:
    """将 'debug' / 'info' 这类字符串统一转换为 logging 级别常量"""
    if isinstance(level, int):
        return level

    if not isinstance(level, str):
        raise ValueError(f'Unknown log level: {level}')

    if level.upper() == 'DEBUG':
        return logging.DEBUG
    else:
        return logging.INFO


def _create_console_handler(level: int, date_fmt: str) -> logging.StreamHandler:
    """创建控制台 handler，输出指定 level 及以上的日志"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt='%(asctime)s [%(levelname)s] %(message)s', 
            datefmt=date_fmt
        )
    )
    return handler


def _create_file_handler(
    path: Path, level: int, date_fmt: str
) -> logging.FileHandler:
    """创建文件 handler，仅记录指定 level 及以上的日志"""
    handler = logging.FileHandler(path, mode='a', encoding='utf-8')
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            fmt='%(asctime)s [%(levelname)s] %(message)s', 
            datefmt=date_fmt
        )
    )
    return handler


def create_logger(
    name: str,
    log_dir: Path,
    level: 'int | str' = 'info',
    use_tqdm: bool = False
) -> TqdmAwareLogger:
    """创建服务日志器"""
    console_level = _resolve_level(level)

    # 切换全局 logger 类，使 logging.getLogger 返回 TqdmAwareLogger
    # setLoggerClass 是全局状态，取完 logger 后立即还原，避免影响其他模块
    old_class = logging.getLoggerClass()
    logging.setLoggerClass(TqdmAwareLogger)
    try:
        logger = logging.getLogger(name)
    finally:
        logging.setLoggerClass(old_class)

    # logging 中同名 logger 是全局单例，重复初始化时清空旧 handler 避免重复输出
    if logger.handlers:
        logger.handlers.clear()

    # 单例由 logging 内部构造，需在此显式同步构造参数
    logger.set_tqdm_enabled(use_tqdm)

    # 日志器自身设为最低级别，交由各 handler 分别过滤
    logger.setLevel(logging.DEBUG)

    console_handler = _create_console_handler(
        console_level, 
        '%Y-%m-%d %H:%M:%S'
    )
    file_handler = _create_file_handler(
        path=Path(log_dir) / 'scripts' / f'{name}.log',
        level=logging.WARNING,
        date_fmt='%Y-%m-%d %H:%M:%S'
    )
    logger.set_handlers(console_handler, file_handler)

    # 阻止日志向 root logger 传播，避免被其他模块的 basicConfig 重复输出
    logger.propagate = False

    return logger

def progress_iterable(
    items: list, 
    entry: str,
    logger: TqdmAwareLogger,
    sample_print: str = None
) -> Iterator:
    """遍历列表，tqdm 模式下用进度条，否则日志输出进度"""
    if logger.use_tqdm:
        tqdm_desc = f'{TimeUtils.log_time()} [INFO] Processing {entry}'
        with tqdm(items, desc=tqdm_desc, total=len(items)) as pbar:
            for item in pbar:
                pbar.set_postfix_str(str(item))
                yield item
    elif sample_print:
        logger.info(
            f'{sample_print}: {len(items)}'
        )
        for idx, item in enumerate(items, 1):
            yield item
    else:
        total = len(items)
        for idx, item in enumerate(items, 1):
            logger.info(
                f'Processing {entry} - [{idx}/{total}] | Current: {item}'
            )
            yield item

def exception_writer(
    log_dir: Path,
    client_id: str,
    error_type: str,
    error_name: str,
    error_info: Optional[str] = None,
    error_id: Optional[str] = None
) -> str:
    """写入异常摘要和详细异常日志"""
    now_iso = TimeUtils.iso_time()

    # 如外部未传入异常 ID 则内部生成
    if error_id is None:
        error_id = str(uuid.uuid4())

    # 检测文件路径是否存在
    if not (log_dir / 'error').exists():
        return 'Log-Dir-Missing'
    if not (log_dir / 'exception').exists():
        return 'Log-Dir-Missing'

    # 将摘要信息写入日志
    log_path = log_dir / 'error' / f'{now_iso.date}.log'
    log_line = f"{now_iso.time},{client_id},{error_name},{error_id}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(log_line)

    # 将具体的错误信息写到本地的单独文件内
    error_path = log_dir / 'exception' / f'{error_id}.log'
    with open(error_path, "a", encoding="utf-8") as f:
        f.write(f"[FROM]:    {client_id}\n")
        f.write(f"[TIME]:    {now_iso.iso}\n")
        f.write(f"[TYPE]:    {error_type}\n")
        f.write(f"[NAME]:    {error_name}\n")
        f.write("\n")
        f.write(error_info or 'No error info')

    return error_id
