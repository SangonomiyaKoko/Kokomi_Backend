import os
from dotenv import load_dotenv


load_dotenv()

CLIENT_NAME = 'SchedulerClan'
LOG_LEVEL = 'debug'
LOG_DIR = '/app/logs'
REFRESH_INTERVAL = 300

# 通过api获取season数据
# 更新SeasonID同时要创建对应的表
# https://developers.wargaming.net/reference/all/wows/clans/season/?language=en&r_realm=asia
SEASON_ID = 32
SEASON_START = 1764568800
SEASON_FINISH = 1770616800

# LOG_DIR = r'F:\Kokomi_PJ_API\logs'

# MYSQL_HOST = '127.0.0.1'
# MYSQL_PORT = 3306
# MYSQL_USERNAME = 'root'
# MYSQL_PASSWORD = 'qazwsxedc0258'

# MAIN_DB = 'game_test'

# REDIS_HOST = '127.0.0.1'
# REDIS_PORT = 6379
# REDIS_PASSWORD = 'qazwsxedc0258'

MYSQL_HOST = os.getenv("MYSQL_HOST")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", 3306))
MYSQL_USERNAME = os.getenv("MYSQL_USERNAME")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD")

MAIN_DB = os.getenv("MAIN_DB")

REDIS_HOST = os.getenv("REDIS_HOST")
REDIS_PORT = os.getenv("REDIS_PORT")
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

'''
CREATE TABLE clan_battle_s32 (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    -- 对局相关信息和ID
    battle_time      TIMESTAMP    NOT NULL,     -- 战斗时间
    region_id        TINYINT      NOT NULL,     -- 服务器id
    clan_id          BIGINT       NOT NULL,     -- 10位的非连续数字
    team_number      TINYINT      NOT NULL,     -- 队伍id
    -- 对局结果
    battle_result    VARCHAR(10)  NOT NULL,     -- 对局结果 胜利或者失败
    battle_rating    VARCHAR(10)  DEFAULT NULL, -- 对局分数 如果是晋级赛则会显示为0
    battle_stage     VARCHAR(10)  DEFAULT NULL, -- 对局结果 仅对于stage有效
    -- 对局结算的数据
    league           TINYINT      DEFAULT NULL, -- 段位 0紫金 1白金 2黄金 3白银 4青铜
    division         TINYINT      DEFAULT NULL, -- 分段 1 2 3
    division_rating  INT          DEFAULT NULL, -- 分段分数，示例：白金 1段 25分
    public_rating    INT          DEFAULT NULL, -- 工会评分 1199 - 3000
    stage_type       VARCHAR(10)  DEFAULT NULL, -- 晋级赛/保级赛 默认为Null
    stage_progress   VARCHAR(50)  DEFAULT NULL, -- 晋级赛/保级赛的当前结果
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 因为数据不会更新，所以不需要updated_at，只需要created_at

    PRIMARY KEY (id), -- 主键

    INDEX idx_time (battle_time), -- 索引

    INDEX idx_cid (clan_id) -- 索引
);
'''