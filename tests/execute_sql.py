import os
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
    "user": 'root',
    "password": 'qazwsxedc0258@',
    "database": os.getenv("MYSQL_DATABASE"),
    'autocommit': False
}
sql = """
-- 1. 新增公会队伍表，结构需与 init/mysql/01-schemas/03-clan.sql 保持一致
CREATE TABLE IF NOT EXISTS T_clan_team (
    id               INT          AUTO_INCREMENT,

    clan_id          BIGINT       NOT NULL,        -- 10位的非连续数字
    season           TINYINT      DEFAULT 0,       -- 赛季 ID
    team_alpha       JSON         DEFAULT NULL,    -- 队伍数据 JSON
    team_bravo       JSON         DEFAULT NULL,    -- 队伍数据 JSON

    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE KEY uk_cid (clan_id)
);

-- 1.1 以 T_clan_base 为准迁移 clan_id，保证两表数据一一对应
INSERT INTO T_clan_team (clan_id)
SELECT clan_id
FROM T_clan_base;

-- 2. 删除 T_clan_stats.team_data
ALTER TABLE T_clan_stats
    DROP COLUMN team_data;

-- 3. 删除 T_ship_base 中已废弃的列
ALTER TABLE T_ship_base
    DROP COLUMN rarity_id,
    DROP COLUMN premium,
    DROP COLUMN special;

-- 4. 调整 T_clan_stats.public_rating 类型为 FLOAT
ALTER TABLE T_clan_stats
    MODIFY COLUMN public_rating FLOAT DEFAULT 1100;

-- 5. 删除 T_clan_stats 中已废弃的列
ALTER TABLE T_clan_stats
    DROP COLUMN stage_battles,
    DROP COLUMN stage_victories;
"""

def main():
    conn = pymysql.connect(**DB_CONFIG)
    try:
        statements = [s.strip() for s in sql.split(';') if s.strip()]
        with conn.cursor() as cursor:
            for stmt in statements:
                cursor.execute(stmt)

        conn.commit()
        logger.info("Execute successfully")
    except Exception:
        conn.rollback()
        logger.exception("Execute failed, rolled back")
        raise
    finally:
        conn.close()


if __name__ == '__main__':
    """执行 sql 语句
    
    使用示例：
    python tests/execute_sql.py
    """

    try:
        main()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")