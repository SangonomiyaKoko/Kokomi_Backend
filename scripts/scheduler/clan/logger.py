import os
import logging

from settings import CLIENT_NAME, LOG_DIR, LOG_LEVEL


def init_logger(level=logging.INFO):
    """初始化日志"""
    logger = logging.getLogger(CLIENT_NAME)
    logger.setLevel(logging.DEBUG)
    if logger.hasHandlers():
        logger.handlers.clear()
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)  # 控制台输出等级
    console_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    error_log_file = os.path.join(LOG_DIR, 'scripts', f'{CLIENT_NAME}_error.log')
    file_handler = logging.FileHandler(error_log_file, mode='a', encoding='utf-8')
    file_handler.setLevel(logging.WARNING)  # 只写 WARNING/ERROR
    file_formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    return logger

if LOG_LEVEL == 'debug':
    logger = init_logger(level=logging.DEBUG)
else:
    logger = init_logger(level=logging.INFO)
