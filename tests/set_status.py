import os
import json
import logging
import argparse
from pathlib import Path
from dotenv import load_dotenv

import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(os.getcwd())

# 加载环境变量
if (ROOT_DIR / 'env.dev').exists():
    logger.info('Loading environment file: env.dev')
    load_dotenv('env.dev')
elif (ROOT_DIR / 'env.prod').exists():
    logger.info('Loading environment file: env.prod')
    load_dotenv('env.prod')
else:
    raise FileNotFoundError('No environment file found')

# API 配置
API_BASE_URL = "http://localhost:8000"
API_ACCESS_TOKEN = os.getenv("API_ROOT_TOKEN")

def main(status: int):
    headers = {
        "Content-Type": "application/json",
        "Access-Token": API_ACCESS_TOKEN
    }
    available = {
        0: 'false',
        1: 'true'
    }.get(status)
    try:
        response = requests.put(
            f"{API_BASE_URL}/api/maintenance/state/?available={available}",
            headers=headers
        )
        response.raise_for_status()
        result = response.json()
        logger.info(f"Response: {json.dumps(result, ensure_ascii=False)}")
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTP error: {e}")
        if e.response is not None:
            logger.error(f"Response body: {e.response.text}")
        raise
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {e}")
        raise


if __name__ == '__main__':
    """修改服务器状态

    使用示例：
    python tests/set_status.py -s 0
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-s', '--status', 
        required=True, 
        type=int, 
        help='Status'
    )
    args = parser.parse_args()
    status = args.status

    try:
        main(
            status=status
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
