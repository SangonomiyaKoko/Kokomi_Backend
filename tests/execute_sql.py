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
CREATE TABLE T_clan_team (
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

INSERT INTO T_clan_team (clan_id)
SELECT clan_id
FROM T_clan_base;

ALTER TABLE T_clan_stats
    DROP COLUMN team_data;

ALTER TABLE T_ship_base
    DROP COLUMN rarity_id,
    DROP COLUMN premium,
    DROP COLUMN special;

ALTER TABLE T_clan_users
    DROP COLUMN member_ids;

ALTER TABLE T_clan_stats
    MODIFY COLUMN public_rating FLOAT DEFAULT 1100;

ALTER TABLE T_base_id
    ADD COLUMN counts INT DEFAULT 0 AFTER meta;

ALTER TABLE T_clan_stats
    DROP COLUMN stage_battles,
    DROP COLUMN stage_victories;

DROP TABLE T_table_meta;
DROP TABLE T_metric_level_thresholds;
DROP FUNCTION F_get_metric_level;
DROP FUNCTION F_clan_next_refresh_at;
DROP FUNCTION F_user_next_refresh_at;
"""

sql = """
CREATE TABLE T_ship_leaderboard (
    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    ship_id          BIGINT       NOT NULL,        -- 1-11位的非连续数字

    battles          INT          NOT NULL,        -- 战斗场次
    rating           FLOAT        NOT NULL,        -- 综合评分
    win_rate         FLOAT        NOT NULL,        -- 胜率
    solo_rate        FLOAT        NOT NULL,        -- 单野率
    avg_damage       INT          NOT NULL,        -- 场均伤害
    avg_frags        FLOAT        NOT NULL,        -- 场均击毁
    avg_exp          INT          NOT NULL,        -- 场均经验
    hit_ratio        FLOAT        NOT NULL,        -- 命中率
    max_exp          INT          NOT NULL,        -- 最高经验
    max_damage       INT          NOT NULL,        -- 最高伤害

    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (ship_id, account_id)
)
PARTITION BY HASH (ship_id)
PARTITIONS 16;

CREATE TABLE T_ship_record (
    id               INT          AUTO_INCREMENT,

    ship_id          BIGINT       UNIQUE,          -- 1-11位的非连续数字
    exp              INT          NOT NULL DEFAULT 0,
    frags            INT          NOT NULL DEFAULT 0,
    planes           INT          NOT NULL DEFAULT 0,
    damage           INT          NOT NULL DEFAULT 0,
    scouting         INT          NOT NULL DEFAULT 0,
    potential        INT          NOT NULL DEFAULT 0,
    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id)
);
INSERT INTO T_ship_record (ship_id)
SELECT ship_id
FROM T_ship_base;

CREATE TABLE T_user_ships (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    user_level       TINYINT      DEFAULT 0,       -- 标记用户水平，为 0 表示数据过少无法评分
    ship_count       INT          DEFAULT 0,       -- payload 中船只数量
    payload          BLOB         DEFAULT NULL,    -- 压缩后的船只数据

    -- 用于标记用户待更新的时间戳，为 0 表示不需要更新, > 0 表示需要更新
    -- 程序读取所有需要更新用户的 pending_at 值并按从早到晚的优先级顺序更新
    pending_at       INT          DEFAULT 0,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id),

    INDEX idx_pending_aid (pending_at, account_id)
);
INSERT INTO T_user_ships (account_id)
SELECT account_id
FROM T_user_base;
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