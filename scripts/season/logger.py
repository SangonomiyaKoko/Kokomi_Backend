import sys
import logging
from tqdm import tqdm
from pathlib import Path

from utils import get_formatted_date
from settings import (
    LOG_DIR,
    USE_TQDM,
    DATE_FMT,
    LOG_LEVEL,
    CLIENT_NAME
)


class TqdmAwareLogger(logging.Logger):
    def __init__(self, name: str, level: int = logging.DEBUG):
        super().__init__(name, level)
        self._use_tqdm = False
        self._console_handler = None
        self._file_handler = None

    def set_handlers(self, console_handler: logging.StreamHandler, file_handler: logging.FileHandler):
        """设置 handlers（在初始化完成后调用）"""
        self._console_handler = console_handler
        self._file_handler = file_handler
        self.addHandler(console_handler)
        self.addHandler(file_handler)

    def enable_tqdm(self) -> None:
        """切换到 tqdm 输出模式"""
        if not self._use_tqdm and USE_TQDM:
            self._use_tqdm = True
            # 移除控制台 handler，但保留文件 handler
            if self._console_handler and self._console_handler in self.handlers:
                self.removeHandler(self._console_handler)

    def disable_tqdm(self) -> None:
        """切换回标准输出模式"""
        if self._use_tqdm:
            self._use_tqdm = False
            # 重新添加控制台 handler
            if self._console_handler and self._console_handler not in self.handlers:
                self.addHandler(self._console_handler)

    def _tqdm_log(self, level: str, msg: str, *args, **kwargs) -> None:
        """通过 tqdm.write 输出日志，同时写入文件"""
        if args:
            try:
                msg = msg % args
            except TypeError:
                msg = msg

        # tqdm 输出到控制台
        tqdm.write(f'{get_formatted_date()} [{level}] {msg}')
        
        # 如果是 WARNING 及以上，写入文件
        level_value = getattr(logging, level, logging.WARNING)
        if level_value >= logging.WARNING and self._file_handler:
            # 直接写入文件
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

    def info(self, msg: str, *args, **kwargs) -> None:
        if self._use_tqdm:
            self._tqdm_log('INFO', msg, *args, **kwargs)
        else:
            super().info(msg, *args, **kwargs)

    def warning(self, msg: str, *args, **kwargs) -> None:
        if self._use_tqdm:
            self._tqdm_log('WARNING', msg, *args, **kwargs)
        else:
            super().warning(msg, *args, **kwargs)

    def debug(self, msg: str, *args, **kwargs) -> None:
        if self._use_tqdm:
            self._tqdm_log('DEBUG', msg, *args, **kwargs)
        else:
            super().debug(msg, *args, **kwargs)

    def error(self, msg: str, *args, **kwargs) -> None:
        if self._use_tqdm:
            self._tqdm_log('ERROR', msg, *args, **kwargs)
        else:
            super().error(msg, *args, **kwargs)


def _create_console_handler(level: int) -> logging.StreamHandler:
    """创建控制台 handler（输出所有 level 及以上日志）"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)  # DEBUG 或 INFO
    handler.setFormatter(logging.Formatter(
        f'%(asctime)s [%(levelname)s] %(message)s',
        datefmt=DATE_FMT
    ))
    return handler


def _create_file_handler() -> logging.FileHandler:
    """创建文件 handler（只记录 WARNING 及以上）"""
    log_path = Path(LOG_DIR) / 'scripts' / f'{CLIENT_NAME}.log'
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    handler = logging.FileHandler(log_path, mode='a', encoding='utf-8')
    handler.setLevel(logging.WARNING)  # 只记录 WARNING 及以上
    handler.setFormatter(logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s',
        datefmt=DATE_FMT
    ))
    return handler


def init_logger(console_level: int = logging.INFO) -> TqdmAwareLogger:
    """初始化 logger
    Args:
        console_level: 控制台输出级别（DEBUG 或 INFO）
    """
    # 保存原 logger 类并设置自定义类
    old_class = logging.getLoggerClass()
    logging.setLoggerClass(TqdmAwareLogger)
    
    # 获取或创建 logger
    logger = logging.getLogger(CLIENT_NAME)
    
    # 恢复默认类
    logging.setLoggerClass(old_class)
    
    # 清除已有的 handlers（避免重复）
    if logger.handlers:
        logger.handlers.clear()
    
    # 设置 logger 级别为最低（DEBUG），让 handler 自己控制
    logger.setLevel(logging.DEBUG)
    
    # 创建 handlers
    console_handler = _create_console_handler(console_level)
    file_handler = _create_file_handler()  # 内部已设置 WARNING 级别
    
    # 设置 handlers 到 logger
    logger.set_handlers(console_handler, file_handler)
    
    # 防止日志传播到 root logger
    logger.propagate = False
    
    return logger


# 初始化
if LOG_LEVEL.lower() == 'debug':
    logger = init_logger(console_level=logging.DEBUG)
else:
    logger = init_logger(console_level=logging.INFO)