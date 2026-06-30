-- 船只基础信息表
-- 存储船只的基本属性，包括等级、类型、国籍、稀有度等
CREATE TABLE IF NOT EXISTS T_ship_base (
    id               INT          AUTO_INCREMENT,

    ship_id          BIGINT       NOT NULL,         -- 1-11位的非连续数字
    is_enabled       BOOLEAN      DEFAULT FALSE,    -- 是否启用统计
    is_old           BOOLEAN      DEFAULT FALSE,    -- 是否为旧船
    tier             TINYINT      DEFAULT 1,        -- 船只等级 1-11
    type_id          TINYINT      DEFAULT 1,        -- 船只类型 ID
    nation_id        TINYINT      DEFAULT 1,        -- 国家 ID
    rarity_id        TINYINT      DEFAULT NULL,     -- 稀有度 ID
    premium          BOOLEAN      DEFAULT FALSE,    -- 是否为金币船
    special          BOOLEAN      DEFAULT FALSE,    -- 是否为特种船
    index_code       VARCHAR(10)  DEFAULT NULL,     -- 索引代码
    ship_name        VARCHAR(50)  DEFAULT NULL,     -- 船只名称

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    INDEX idx_tier (tier),
    INDEX idx_type (type_id),
    INDEX idx_nation (nation_id),
    UNIQUE INDEX idx_sid (ship_id),
    UNIQUE INDEX idx_rank_sid (is_enabled, is_old, tier, ship_id)
);

-- 船只 PvP 统计表
-- 存储基于所有用户 PvP 缓存数据汇总的全局总量与单船统计
CREATE TABLE IF NOT EXISTS T_ship_pvp_stats (
    id               INT          AUTO_INCREMENT,

    ship_id            BIGINT      NOT NULL,
    ship_users         INT         DEFAULT 0,
    total_battles      BIGINT      DEFAULT 0,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_sid (ship_id)
);

-- 船只服务器场次统计表
-- 存储基于所有用户战斗场次计算的服务器平均数据
CREATE TABLE IF NOT EXISTS T_ship_stats_by_battles (
    id               BIGINT       AUTO_INCREMENT,

    ship_id          BIGINT       NOT NULL,         -- 1-11位的非连续数字
    battles          BIGINT       DEFAULT 0,        -- 总战斗场次
    win_rate         FLOAT        DEFAULT 0,        -- 胜率（%）
    avg_damage       FLOAT        DEFAULT 0,        -- 场均伤害
    avg_frags        FLOAT        DEFAULT 0,        -- 场均击毁
    avg_exp          FLOAT        DEFAULT 0,        -- 场均经验
    survived_rate    FLOAT        DEFAULT 0,        -- 存活率（%）
    avg_scouting_damage INT       DEFAULT 0,        -- 场均侦查伤害
    avg_potential_damage INT      DEFAULT 0,        -- 场均潜在伤害

    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_sid (ship_id)
);

-- 船只用户维度统计表
-- 存储基于有效用户（battles > 10）计算的用户平均水平
CREATE TABLE IF NOT EXISTS T_ship_stats_by_users (
    id               BIGINT       AUTO_INCREMENT,

    ship_id          BIGINT       NOT NULL,         -- 1-11位的非连续数字
    users            INT          DEFAULT 0,        -- 有效用户数
    battles          BIGINT       DEFAULT 0,        -- 总战斗场次
    rating           INT          DEFAULT -1,       -- 用户平均 Rating
    win_rate         FLOAT        DEFAULT 0,        -- 用户平均胜率（%）
    avg_damage       FLOAT        DEFAULT 0,        -- 用户平均场均伤害
    avg_frags        FLOAT        DEFAULT 0,        -- 用户平均场均击毁
    avg_exp          FLOAT        DEFAULT 0,        -- 用户平均场均经验
    survived_rate    FLOAT        DEFAULT 0,        -- 用户平均存活率（%）
    avg_scouting_damage INT       DEFAULT 0,        -- 用户平均场均侦查伤害
    avg_potential_damage INT      DEFAULT 0,        -- 用户平均场均潜在伤害

    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_sid (ship_id)
);

-- 船只 Rating 分布统计表
-- 存储各船只用户 Rating 的百分位分布数据
CREATE TABLE IF NOT EXISTS T_ship_rating_distribution (
    id               BIGINT       AUTO_INCREMENT,

    ship_id          BIGINT       NOT NULL,
    sample_count     INT          NOT NULL DEFAULT 0,   -- 样本数量
    top1             FLOAT        NOT NULL DEFAULT 0.0, -- 前1%阈值
    top5             FLOAT        NOT NULL DEFAULT 0.0, -- 前5%阈值
    top10            FLOAT        NOT NULL DEFAULT 0.0, -- 前10%阈值
    top15            FLOAT        NOT NULL DEFAULT 0.0, -- 前15%阈值
    top50            FLOAT        NOT NULL DEFAULT 0.0, -- 中位数
    top75            FLOAT        NOT NULL DEFAULT 0.0, -- 前75%阈值
    top90            FLOAT        NOT NULL DEFAULT 0.0, -- 前90%阈值

    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_ship (ship_id)
);

-- 船只 PvP 极值记录表
-- 存储各船只各项指标的最高记录及达成用户
CREATE TABLE IF NOT EXISTS T_ship_pvp_record (
    id               INT          AUTO_INCREMENT,

    ship_id          BIGINT       NOT NULL,        -- 1-11位的非连续数字
    metric_id        INT          NOT NULL,        -- 关联 D_metric_name
    metric_value     INT          DEFAULT 0,       -- 指标最高值
    users_count      INT          DEFAULT 0,       -- 到达该值的用户数
    top_user_ids     JSON         DEFAULT NULL,    -- 记录此指标最高的用户ID集合

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_sid_mid (ship_id, metric_id)
);

-- 船只 PvP 排行榜表
-- 存储玩家在各船只上的战斗表现，按 Rating 排名
CREATE TABLE IF NOT EXISTS T_ship_pvp_leaderboard (
    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    ship_id          BIGINT       NOT NULL,        -- 1-11位的非连续数字

    battles          INT          NOT NULL,        -- 战斗场次
    rating           FLOAT        NOT NULL,        -- 综合评分
    win_rate         FLOAT        NOT NULL,        -- 胜率
    avg_damage       INT          NOT NULL,        -- 场均伤害
    avg_damage_level TINYINT      NOT NULL,        -- 伤害等级 1-5
    avg_frags        FLOAT        NOT NULL,        -- 场均击毁
    avg_frags_level  TINYINT      NOT NULL,        -- 击毁等级 1-5
    avg_exp          INT          NOT NULL,        -- 场均经验
    hit_ratio        FLOAT        NOT NULL,        -- 命中率
    max_exp          INT          NOT NULL,        -- 最高经验
    max_damage       INT          NOT NULL,        -- 最高伤害

    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (ship_id, account_id)
)
PARTITION BY HASH (ship_id)
PARTITIONS 16;

-- 船只 Recent 数据归档表
-- 按版本号归档从 Recent API 拉取的船只战斗原始数据
CREATE TABLE IF NOT EXISTS ARCH_ship_stats_by_recent (
    id               BIGINT       AUTO_INCREMENT,

    ship_id          BIGINT       NOT NULL,
    game_version     VARCHAR(10)  NOT NULL,        -- 游戏版本号
    battles          INT          NOT NULL DEFAULT 0,
    wins             INT          NOT NULL DEFAULT 0,
    damage           BIGINT       NOT NULL DEFAULT 0,
    frags            INT          NOT NULL DEFAULT 0,
    exp              BIGINT       NOT NULL DEFAULT 0,
    survived         INT          NOT NULL DEFAULT 0,
    scouting_damage  BIGINT       NOT NULL DEFAULT 0,
    potential_damage BIGINT       NOT NULL DEFAULT 0,

    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_ship_version (ship_id, game_version),

    INDEX idx_version (game_version),
    INDEX idx_ship (ship_id)
);

-- 船只 Recent 数据暂存表
-- 从 API 拉取的原始数据先写入此表，再由后台任务消费处理
CREATE TABLE IF NOT EXISTS STAGING_ship_recent_data (
    uuid            CHAR(36)     NOT NULL,          -- 唯一标识

    status          ENUM('pending', 'done', 'error') DEFAULT 'pending',  -- 处理状态
    game_version    VARCHAR(10)  NOT NULL,          -- 游戏版本号
    account_id      BIGINT       NOT NULL,          -- 用户 ID
    payload         JSON         NOT NULL,          -- 原始数据

    created_at      TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    processed_at    TIMESTAMP    DEFAULT NULL,      -- 处理完成时间

    PRIMARY KEY (uuid),

    KEY idx_consumer (status, created_at)
);