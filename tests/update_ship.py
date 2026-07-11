import os
import csv
import json
import logging
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

# 读取区域配置
file_path = ROOT_DIR / 'data/json/init_marker.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    REGION: str = data['region']


def parse_ship_row(row: dict) -> list:
    """将 CSV 行解析为 API 所需的船只数据列表
    返回: [is_old, tier, type_id, nation_id, rarity_id, premium, special, index_code, ship_name]
    """
    return [
        int(row.get('is_old', 0)),
        int(row['tier']),
        int(row['type_id']),
        int(row['nation_id']),
        int(row['rarity_id']) if row.get('rarity_id') else 0,
        int(row.get('premium', 0)),
        int(row.get('special', 0)),
        row.get('index', ''),
        row.get('default', '')
    ]


def build_request_payload(raw_ships: list[dict]) -> dict:
    """将 CSV 行列表转换为 API 请求体格式
    格式: { ship_id: [is_old, tier, type_id, nation_id, rarity_id, premium, special, index_code, ship_name], ... }
    """
    payload = {}
    for row in raw_ships:
        ship_id = row['ship_id']
        payload[ship_id] = parse_ship_row(row)
    return payload


def main(filepath: Path):
    """从 CSV 文件读取船只数据并通过 API 刷新数据库"""
    if not filepath.exists():
        logger.error(f"CSV file not found: {filepath}")
        return

    # 读取并解析 CSV
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.DictReader(f)
            raw_ships = list(reader)
        logger.info(f'Found {len(raw_ships)} ships in CSV')
    except Exception as e:
        logger.error(f"Failed to read CSV: {e}")
        return

    if not raw_ships:
        logger.warning('No ships to process, exiting')
        return

    # 构建请求体
    payload = build_request_payload(raw_ships)
    logger.info(f'Built payload with {len(payload)} ships')

    # 发送 API 请求
    headers = {
        "Content-Type": "application/json",
        "Access-Token": API_ACCESS_TOKEN
    }

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/maintenance/ship/refresh/",
            json=payload,
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
    """船只数据更新工具 —— 通过 API 接口更新

    使用示例:
    python tests/update_ship.py
    """
    if REGION == 'ru':
        filepath = ROOT_DIR / 'init/data/ship_name_lesta.csv'
    else:
        filepath = ROOT_DIR / 'init/data/ship_name_wg.csv'

    try:
        main(filepath)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
