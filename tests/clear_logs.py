import os
import json
import logging
from pathlib import Path


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(os.getcwd())

file_path = ROOT_DIR / 'data/const/constants.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    SERVICE_LIST: list = data['SERVICE_LIST']

def main():
    """删除所有错误日志文件"""
    error_dir = ROOT_DIR / 'logs/error'
    exception_dir = ROOT_DIR / 'logs/exception'

    del_count = 0
    for log_dir in (error_dir, exception_dir):
        if log_dir.exists() and log_dir.is_dir():
            for file_path in log_dir.glob('*'):
                if file_path.is_file():
                    file_path.unlink()
                    del_count += 1
    logger.info(f'Delete logs: {del_count}')

    clear_count = 0
    for service in SERVICE_LIST:
        log_file = ROOT_DIR / 'logs/scripts' / f'{service}.log'
        if log_file.exists():
            log_file.write_text('')
            clear_count += 1
    logger.info(f'Clear files: {clear_count}')

if __name__ == '__main__':
    """清理错误日志

    使用示例：
    python tests/clear_logs.py
    """
    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")