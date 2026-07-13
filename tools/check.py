import os
import json
import logging
import pymysql
import argparse
from tqdm import tqdm
from pathlib import Path
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(os.getcwd())

if (ROOT_DIR / 'env.dev').exists():
    load_dotenv('env.dev')
elif (ROOT_DIR / 'env.prod').exists():
    load_dotenv('env.prod')
else:
    raise FileNotFoundError('No environment file found')

DB_CONFIG = {
    "host": 'localhost',
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    "autocommit": False
}

file_path = ROOT_DIR / 'data/const/constants.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
USER_INIT_TABLE_LIST = data['USER_INIT_TABLE_LIST']
CLAN_INIT_TABLE_LIST = data['CLAN_INIT_TABLE_LIST']
SHIP_INIT_TABLE_LIST = data['SHIP_INIT_TABLE_LIST']

BATCH_SIZE = 10000

def load_base_data(cursor, id_col: str, base_table: str) -> tuple:
    logger.info(f"Loading table {base_table}...")
    
    cursor.execute(f"SELECT MAX(id) FROM {base_table};")
    max_id = cursor.fetchone()[0] or 0
    logger.info(f"Table MaxID: {max_id}")

    if max_id == 0:
        logger.warning(f"Table {base_table} is empty")
        return set(), [], 0

    account_ids = set()
    missing_ids = []
    expected_id = 1

    total_batches = (max_id + BATCH_SIZE - 1) // BATCH_SIZE

    with tqdm(total=max_id, desc="Loading user base", unit="rows") as pbar:
        for batch_idx in range(total_batches):
            start_id = batch_idx * BATCH_SIZE + 1
            end_id = min(start_id + BATCH_SIZE - 1, max_id)
            
            sql = f"""
                SELECT id, {id_col}  
                FROM {base_table}
                WHERE id BETWEEN %s AND %s
                ORDER BY id ASC;
            """
            cursor.execute(sql, [start_id, end_id])
            rows = cursor.fetchall()

            if not rows:
                for i in range(start_id, end_id + 1):
                    missing_ids.append(i)
                expected_id = end_id + 1
                pbar.update(end_id - start_id + 1)
                continue

            for (current_id, account_id) in rows:
                while expected_id < current_id:
                    missing_ids.append(expected_id)
                    expected_id += 1
                account_ids.add(account_id)
                expected_id = current_id + 1

            pbar.update(end_id - start_id + 1)

    if missing_ids:
        logger.warning(f"❌  Found {len(missing_ids)} missing auto-increment IDs")
    else:
        logger.info("✅  Auto-increment IDs are fully continuous")

    return account_ids, missing_ids, max_id

def check_table_integrity(cursor, id_col: str, table_name: str, base_account_ids: set) -> dict:
    logger.info(f"Checking table {table_name}...")
    
    cursor.execute(f"SELECT MAX(id) FROM {table_name};")
    max_id = cursor.fetchone()[0] or 0

    if max_id == 0:
        logger.warning(f"Table {table_name} is empty")
        return {
            'max_id': 0,
            'missing_count': len(base_account_ids),
            'orphan_count': 0,
            'missing': set(),
            'orphan': set()
        }

    table_account_ids = set()

    with tqdm(total=max_id, desc=f"Checking {table_name}", unit="rows") as pbar:
        for start_id in range(1, max_id + 1, BATCH_SIZE):
            end_id = min(start_id + BATCH_SIZE - 1, max_id)

            sql = f"""
                SELECT {id_col} 
                FROM {table_name}
                WHERE id BETWEEN %s AND %s
            """
            cursor.execute(sql, [start_id, end_id])
            rows = cursor.fetchall()

            for (account_id,) in rows:
                table_account_ids.add(account_id)

            pbar.update(end_id - start_id + 1)

    missing = base_account_ids - table_account_ids
    orphan = table_account_ids - base_account_ids

    if missing:
        logger.warning(f"❌  Missing {len(missing)} account_ids")
        if len(missing) <= 100:
            logger.warning(missing)
    else:
        logger.info(f"✅  No missing records")

    if orphan:
        logger.warning(f"❌  Orphan {len(orphan)} account_ids")
        if len(orphan) <= 100:
            logger.warning(orphan)
    else:
        logger.info(f"✅  No orphan records")

    return {
        'max_id': max_id,
        'missing_count': len(missing),
        'orphan_count': len(orphan),
        'missing': missing,
        'orphan': orphan
    }

def check_report(
    index: str, 
    base_table: str, 
    base_max_id: int, 
    id_count: int,
    missing_ids: list, 
    results: list
) -> None:
    """输出数据完整性报告"""
    id_cont = "✅" if not missing_ids else "❌"
    base_missing_str = str(len(missing_ids)) if missing_ids else "/"
    logger.info("")
    logger.info(f"{index.capitalize()} Data Integrity Check Report:")
    logger.info("=" * 70)
    logger.info(f"{'Table':<30} {'MaxID':>8} {'IDCont':>6} {'Missing':>8} {'Orphan':>8}")
    logger.info("-" * 70)
    logger.info(f"{base_table:<30} {base_max_id:>8} {id_cont:>6} {base_missing_str:>8} {'/':>8}")

    for table_name, r in results:
        miss_str = str(r['missing_count']) if r['missing_count'] else "✅"
        orph_str = str(r['orphan_count']) if r['orphan_count'] else "✅"
        logger.info(f"{table_name:<30} {r['max_id']:>8} {'/':>6} {miss_str:>8} {orph_str:>8}")

    logger.info("-" * 70)
    logger.info(f"Total {index}s: {id_count}")
    if missing_ids:
        logger.info(f"Total missing auto-increment IDs in base: {len(missing_ids)}")
    total_missing = sum(r['missing_count'] for _, r in results)
    total_orphan = sum(r['orphan_count'] for _, r in results)
    logger.info(f"Total missing records across tables: {total_missing}")
    logger.info(f"Total orphan records across tables: {total_orphan}")
    logger.info("=" * 70)

def export_abnormal_ids(index: str, all_abnormal_ids: set) -> str:
    """
    导出异常用户 id 到 JSON 文件。

    参数:
        index: 类型标识 ('user'/'clan'/'ship')
        all_abnormal_ids: 去重后的异常 id 集合

    返回:
        导出文件路径
    """
    trash_dir = ROOT_DIR / 'data/trash'
    trash_dir.mkdir(parents=True, exist_ok=True)

    export_path = trash_dir / f'abnormal_{index}_ids.json'
    with open(export_path, 'w', encoding='utf-8') as f:
        json.dump(sorted(list(all_abnormal_ids)), f, ensure_ascii=False, indent=2)

    logger.info(f"Abnormal {index} IDs exported to: {export_path}")
    return str(export_path)

def main(index: str):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            table_name_list = {
                'user': USER_INIT_TABLE_LIST,
                'clan': CLAN_INIT_TABLE_LIST,
                'ship': SHIP_INIT_TABLE_LIST
            }.get(index)
            id_col = {
                'user': 'account_id',
                'clan': 'clan_id',
                'ship': 'ship_id'
            }.get(index)
            base_table = f'T_{index}_base'
            
            account_ids, missing_ids, base_max_id = load_base_data(cursor, id_col, base_table)
            id_count = len(account_ids)
            
            if id_count == 0:
                logger.warning(f"No data in {base_table}, check aborted")
                return

            results = []
            all_abnormal_ids = set()

            for table_name in table_name_list:
                logger.info('=' * 50)
                result = check_table_integrity(cursor, id_col, table_name, account_ids)
                results.append((table_name, result))
                # 汇总异常 id（missing 和 orphan 合并去重）
                all_abnormal_ids.update(result['missing'])
                all_abnormal_ids.update(result['orphan'])

            check_report(index, base_table, base_max_id, id_count, missing_ids, results)

            # 导出异常 id
            if all_abnormal_ids:
                export_abnormal_ids(index, all_abnormal_ids)

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    """数据库数据完整性检测脚本

    运行前请确保所有子服务已停止运行，避免读取到异常数据或影响服务正常运行

    使用示例：
    python tools/check.py -i user
    python tools/check.py -i clan
    python tools/check.py -i ship
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i", "--index",
        type=str,
        required=True,
        help="Index"
    )
    args = parser.parse_args()
    index = args.index
    if index not in ['user', 'clan', 'ship']:
        raise ValueError('Incorrect index')
    
    try:
        main(index)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")