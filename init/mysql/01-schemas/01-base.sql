-- 指标名称字典表
-- 存储用户 PvP 记录中各项指标的名称，如 max_exp、max_damage 等
CREATE TABLE IF NOT EXISTS D_metric_name (
    id               INT          AUTO_INCREMENT,

    name             VARCHAR(20)  NOT NULL,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id)
);

-- 排行榜场次限制字典表
-- 定义各等级船只上榜所需的最小战斗场次
CREATE TABLE IF NOT EXISTS D_ranking_battles_limit (
    id               INT          AUTO_INCREMENT,

    tier             INT          NOT NULL,      -- 船只等级
    battles_limit    INT          NOT NULL,      -- 场次限制

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_tier (tier)
);

-- 游戏版本表
-- 记录各游戏版本的名称和是否为最新版本
CREATE TABLE IF NOT EXISTS T_game_version (
    id               INT          AUTO_INCREMENT,

    is_latest        BOOLEAN      DEFAULT FALSE,
    short_name       VARCHAR(10)  NOT NULL,
    full_name        VARCHAR(100) NOT NULL,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    INDEX idx_name (short_name)
);

-- 数据追踪元信息表
-- 记录各类数据更新任务的上次执行时间，用于判断是否需要重新执行
CREATE TABLE IF NOT EXISTS T_tracking_meta (
    id              INT           AUTO_INCREMENT,

    tracking_key    VARCHAR(50)   NOT NULL,         -- 跟踪键，如 clan、ship 等
    tracking_type   VARCHAR(20)   NOT NULL,         -- 类型：refresh_time / update_time / archive_time
    tracking_value  TIMESTAMP     DEFAULT NULL,     -- 上次执行的时间戳

    created_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_key_type (tracking_key, tracking_type)
);

-- 表数据量元信息表
-- 记录各业务表的数据行数，用于监控数据增长
CREATE TABLE IF NOT EXISTS T_table_meta (
    id              INT           AUTO_INCREMENT,

    metric_key      VARCHAR(50)   NOT NULL,         -- 统计键，通常为表名
    metric_value    BIGINT        DEFAULT 0,        -- 数据行数
    table_name      VARCHAR(50)   NOT NULL,         -- 数据来源表名

    created_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_key (metric_key)
);

-- 数据库元信息表
-- 记录数据库的数据，用于监控数据增长
CREATE TABLE IF NOT EXISTS T_database_meta (
    id              INT           AUTO_INCREMENT,

    metric_key      VARCHAR(50)   NOT NULL,         -- 统计键，通常为表名
    metric_value    BIGINT        DEFAULT 0,        -- 数据行数

    created_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_key (metric_key)
);

-- 元数据ID信息表
-- 记录实体ID的范围
CREATE TABLE IF NOT EXISTS T_base_id (
    id              INT           AUTO_INCREMENT,

    meta            VARCHAR(5)    NOT NULL,         -- 统计键，通常为表名
    min_id          BIGINT        DEFAULT 0,        -- 数据行数
    max_id          BIGINT        DEFAULT 0,        -- 数据行数

    created_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP     DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_meta (meta)
);

-- 指标等级阈值表
-- 定义各项指标等级评定的阈值，用于 F_get_metric_level 函数
CREATE TABLE IF NOT EXISTS T_metric_level_thresholds (
    id               INT          AUTO_INCREMENT,

    metric_id        INT          NOT NULL,        -- 指标 ID
    threshold        FLOAT        NOT NULL,        -- 阈值

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    INDEX idx_mid (metric_id)
);

CREATE TABLE IF NOT EXISTS T_refresh_stats (
    id               INT          AUTO_INCREMENT,

    status           VARCHAR(50)  NOT NULL, -- '状态标识: overdue/today/within_week/within_month/within_quarter',
    user_count       INT NOT NULL DEFAULT 0,
    clan_count       INT NOT NULL DEFAULT 0,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_status (status)
);

CREATE TABLE IF NOT EXISTS T_refresh_hourly_stats (
    id               INT          AUTO_INCREMENT,

    planned_hour     TINYINT       NOT NULL,
    planned_users    INT           DEFAULT 0,
    planned_clans    INT           DEFAULT 0,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_hour (planned_hour)
);

-- 基础数据归档表
-- 按日期记录基础表的行数变化
CREATE TABLE IF NOT EXISTS ARCH_base_count (
    id               BIGINT       AUTO_INCREMENT,

    stat_date        DATE         NOT NULL,        -- 统计日期 YYYY-MM-DD
    total_count      INT          NOT NULL,        -- 当日数据条目数
    user_count       INT          NOT NULL,        -- 当日数据条目数
    clan_count       INT          NOT NULL,        -- 当日数据条目数
    ship_count       INT          NOT NULL,        -- 当日数据条目数

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE KEY uk_date (stat_date)
);