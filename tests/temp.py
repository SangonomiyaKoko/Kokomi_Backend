import os
import csv
import time
import json
import logging
import pymysql
from pathlib import Path
from dotenv import load_dotenv
from datetime import datetime, date

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

# 读取区域配置
file_path = ROOT_DIR / 'data/json/init_marker.json'
with open(file_path, "r", encoding="utf-8") as f:
    data = json.load(f)
    REGION: str = data['region']

DB_CONFIG = {
    "host": 'localhost',
    "port": int(os.getenv("MYSQL_PORT", 3306)),
    "user": os.getenv("MYSQL_USER"),
    "password": os.getenv("MYSQL_PASSWORD"),
    "database": os.getenv("MYSQL_DATABASE"),
    'autocommit': False
}

def convert_row_timestamps(row):
    """
    将行中的 datetime/date 对象转换为时间戳，其他保持不变
    
    Args:
        row: 元组或列表
    
    Returns:
        list: 转换后的列表
    """
    converted = []
    for value in row:
        if isinstance(value, datetime):
            # datetime 转时间戳
            converted.append(int(value.timestamp()))
        elif isinstance(value, date):
            # date 转时间戳
            dt = datetime(value.year, value.month, value.day)
            converted.append(int(dt.timestamp()))
        else:
            # 其他类型保持不变
            converted.append(value)
    return converted

def main(filepath: Path):
    """
    迁移 T_ship_base 表数据，只保留指定的 ship_id
    
    执行步骤：
    1. 创建临时表 T_ship_base_tmp（结构与原表一致）
    2. 从原表读取数据，按指定的 ship_id 列表过滤并插入临时表
    3. 删除原表
    4. 重命名临时表为原表名
    """
    
    keep_ship_ids = []
    try:
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            reader = csv.reader(f)
            # 跳过表头
            next(reader, None)
            for row in reader:
                if row and row[0].strip():
                    keep_ship_ids.append(int(row[0].strip()))
        logger.info(f"从CSV文件读取到 {len(keep_ship_ids)} 个ship_id")
    except Exception as e:
        logger.error(f"读取CSV文件失败: {e}")
        raise

    if not keep_ship_ids:
        logger.warning("keep_ship_ids 列表为空，没有数据需要保留")
        return
    
    table_name_list = [
        'T_ship_base', 
        'T_ship_pvp_record', 
        'T_ship_pvp_stats', 
        'T_ship_rating_distribution', 
        'T_ship_stats_by_battles', 
        'T_ship_stats_by_users', 
        'ARCH_ship_stats_by_recent'
    ]
    
    conn = pymysql.connect(**DB_CONFIG)

    try:
        all_tables_data = {}
        backup_file = ROOT_DIR / 'data/trash/ship_backup.json'

        with conn.cursor() as cursor:
            for table_name in table_name_list:
                # 重命名原表
                logger.info(f"重命名原表为 _{table_name}")
                cursor.execute(f"RENAME TABLE {table_name} TO _{table_name};")

                # 创建临时表（结构与原表一致）
                logger.info(f"创建原表 {table_name}")
                cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} LIKE _{table_name};")

                # 先查询所有数据，区分保留和未保留的
                cursor.execute(f"SELECT * FROM _{table_name} ORDER BY id;")
                all_rows = cursor.fetchall()

                converted_rows = []
                for row in all_rows:
                    converted_rows.append(convert_row_timestamps(row))
                
                # 直接以表名为 key，value 是行列表
                all_tables_data[table_name] = converted_rows

                # 获取列名
                cursor.execute(f"""
                    SELECT COLUMN_NAME 
                    FROM INFORMATION_SCHEMA.COLUMNS 
                    WHERE TABLE_SCHEMA = '{DB_CONFIG['database']}' 
                    AND TABLE_NAME = '_{table_name}' 
                    ORDER BY ORDINAL_POSITION;
                """)
                columns = [row[0] for row in cursor.fetchall()]

                # 分离保留和未保留的数据
                keep_rows = []
                remove_rows = []
                keep_set = set(keep_ship_ids)

                # 创建ship_id到行索引的映射，用于快速查找
                for row in all_rows:
                    if row[1] in keep_set:
                        keep_rows.append(row[1:])
                    else:
                        remove_rows.append(row[1:])

                logger.info(f"原表总数据: {len(all_rows)} 条")
                logger.info(f"需要保留: {len(keep_rows)} 条")
                logger.info(f"需要删除: {len(remove_rows)} 条")

                # 输出所有未保留的船只数据行
                if remove_rows:
                    logger.info("=" * 60)
                    logger.info("将被删除的船只数据 (未保留):")
                    logger.info("=" * 60)
                    for row in remove_rows:
                        logger.info(row)
                    logger.info("=" * 60)

                # 插入保留的数据到临时表（保持原顺序）
                if keep_rows:
                    # 构建插入SQL
                    placeholders = ', '.join(['%s'] * len(columns[1:]))
                    cursor.executemany(f"""
                    INSERT INTO {table_name} ({', '.join(columns[1:])}) 
                    VALUES ({placeholders});
                    """, keep_rows)
                    inserted_count = len(keep_rows)
                    logger.info(f"成功迁移 {inserted_count} 条记录到临时表")
                else:
                    logger.warning("没有需要保留的数据")
                    inserted_count = 0

                conn.commit()
                logger.info("数据迁移完成！")

                with open(backup_file, 'w', encoding='utf-8') as f:
                    json.dump(all_tables_data, f)

                time.sleep(10)
            
            for table_name in table_name_list:
                cursor.execute(f"DROP TABLE _{table_name};")
            conn.commit()
            logger.info("临时表删除完成！")
    except Exception as e:
        conn.rollback()
        logger.exception(f"数据迁移失败，已回滚所有操作: {e}")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    """执行船只基础表数据迁移
    
    功能：从 T_ship_base 表中筛选并保留指定的 ship_id 数据
    使用示例：
        python tests/temp.py
    """
    if REGION == 'ru':
        filepath = ROOT_DIR / 'init/data/ship_name_lesta.csv'
    else:
        filepath = ROOT_DIR / 'init/data/ship_name_wg.csv'

    try:
        main(filepath)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")