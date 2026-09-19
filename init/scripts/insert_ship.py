import os
import csv
import json
import logging
import pymysql
from pathlib import Path
from dotenv import load_dotenv

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

DB_CONFIG = {
    "host": 'localhost',
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    'autocommit': False
}

# 读取区域配置
file_path = ROOT_DIR / 'data/json/init_marker.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    REGION: str = data['region']

SHIP_INIT_TABLE_LIST = [
    "T_ship_pvp_stats",
    "T_ship_stats_by_battles",
    "T_ship_stats_by_users",
    "T_ship_rating_distribution"
]

# 需要初始化的 PvP 极值记录指标 ID
METRIC_IDS = [3, 4, 5, 7, 8, 9]


def parse_ship_row(row: dict) -> dict:
    """将 CSV 行解析为用于插入的船只参数字典"""
    return {
        'ship_id': int(row['ship_id']),
        'is_old': bool(int(row.get('is_old', 0))),
        'tier': int(row['tier']),
        'type_id': int(row['type_id']),
        'nation_id': int(row['nation_id']),
        'index': row.get('index', ''),
        'default_name': row.get('default', '')
    }


def main(filepath: Path):
    """从CSV文件批量初始化所有船只相关表（空数据库插入模式）"""
    if not filepath.exists():
        logger.error(f"CSV file not found: {filepath}")
        return

    # 读取并解析CSV，保持顺序
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

    ships = [parse_ship_row(row) for row in raw_ships]
    logger.info(f"Parsed {len(ships)} ships")

    # T_ship_base 数据
    base_data = []
    for s in ships:
        base_data.append((
            s['ship_id'],
            True,               # is_enabled
            s['is_old'],
            s['tier'],
            s['type_id'],
            s['nation_id'],
            s['index'],         # index_code
            s['default_name']   # ship_name
        ))

    # 关联统计表数据
    init_table_data = [[(s['ship_id'],) for s in ships] for _ in SHIP_INIT_TABLE_LIST]

    # T_ship_pvp_record 数据（每个 ship 对应多个 metric_id）
    pvp_data = []
    for s in ships:
        for metric_id in METRIC_IDS:
            pvp_data.append((s['ship_id'], metric_id))

    conn = pymysql.connect(**DB_CONFIG)
    try:
        # 插入主表 T_ship_base
        sql_base = """
            INSERT INTO T_ship_base (
                ship_id, is_enabled, is_old, tier, type_id,
                nation_id, index_code, ship_name
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        with conn.cursor() as cursor:
            cursor.executemany(sql_base, base_data)
        conn.commit()
        logger.info(f"Inserted {len(ships)} rows into T_ship_base")

        # 依次插入各关联统计表
        for table_name, data_batch in zip(SHIP_INIT_TABLE_LIST, init_table_data):
            sql_init = f"INSERT INTO {table_name} (ship_id) VALUES (%s)"
            with conn.cursor() as cursor:
                cursor.executemany(sql_init, data_batch)
            conn.commit()
            logger.info(f"Inserted {len(ships)} rows into {table_name}")

        # 插入 PvP 极值记录表
        sql_pvp = """
            INSERT INTO T_ship_pvp_record (ship_id, metric_id) VALUES (%s, %s)
        """
        with conn.cursor() as cursor:
            cursor.executemany(sql_pvp, pvp_data)
        conn.commit()
        logger.info(f"Inserted {len(pvp_data)} rows into T_ship_pvp_record")
    except Exception:
        conn.rollback()
        logger.exception("Insertion failed, rolled back")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    """船只数据初始化工具（仅插入模式）
    
    使用示例：
    python init/scripts/insert_ship.py
    """
    if REGION == 'ru':
        filepath = ROOT_DIR / 'init/data/ship_name_lesta.csv'
    else:
        filepath = ROOT_DIR / 'init/data/ship_name_wg.csv'

    try:
        main(filepath)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")