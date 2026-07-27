-- 注意：以下数据库设计均为 SQLite3 数据库


-- 船只单日快照数据表
-- 存储某一日期、某一艘船的战绩快照，是数据最小粒度
CREATE TABLE IF NOT EXISTS ship_daily_snapshot (
    id               INTEGER      PRIMARY KEY,

    ship_id          INT          NOT NULL,                    -- 船只ID
    snapshot_date    INT          NOT NULL,                    -- 快照日期，格式：YYYYMMDD
    snapshot_data    TEXT         NOT NULL,                    -- JSON序列化后的船只战绩数据

    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ship_id, snapshot_date)                            -- 每艘船每天仅一条快照
);


-- 最新船只快照缓存表
-- 记录每艘船最新一次快照的索引及基础战斗数
CREATE TABLE IF NOT EXISTS ship_latest_cache (
    id               INTEGER      PRIMARY KEY,

    ship_id          INT          UNIQUE,                     -- 船只ID（唯一）
    battles          INT          DEFAULT 0,                  -- 该船总战斗场次
    snapshot_date    INT          NOT NULL,                   -- 该船最新快照所在日期

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO ship_latest_cache (ship_id, battles, snapshot_date) VALUES (1000000000, 0, NULL);

-- 日期-快照映射表
-- 将一个日期下的所有船只快照索引打包成JSON对象
CREATE TABLE IF NOT EXISTS daily_snapshot_index (
    id                INTEGER      PRIMARY KEY,

    snapshot_date     INT          UNIQUE,                    -- 快照日期，格式：YYYYMMDD（唯一）
    ship_count        INT          DEFAULT 0,                 -- 该映射刷新时间
    ship_map          TEXT         NOT NULL,                  -- 该映射刷新时间

    updated_at        DATETIME     DEFAULT CURRENT_TIMESTAMP
);


-- 用户每日摘要表
-- 每一个日期一行，记录当日快照的概要信息
CREATE TABLE IF NOT EXISTS user_daily_summary (
    id               INTEGER      PRIMARY KEY,

    snapshot_date    INT          UNIQUE,                     -- 快照日期，格式：YYYYMMDD（唯一）
    is_public        BOOLEAN      NOT NULL,                   -- 用户是否公开战绩
    total_battles    INT          DEFAULT 0,                  -- 总战斗场次
    pve_battles      INT          DEFAULT 0,                  -- PvE战斗场次
    pvp_battles      INT          DEFAULT 0,                  -- PvP战斗场次
    ranked_battles   INT          DEFAULT 0,                  -- 排位战斗场次
    karma            INT          DEFAULT 0,                  -- 业力值
    index_table      TEXT         DEFAULT NULL,               -- 固定值 'daily_snapshot_index'，指向映射表

    updated_at       INT          DEFAULT NULL
);


-- 用户近期详细数据统计表
-- 每条记录对应一艘船的某个战斗模式的各项战绩变化量
CREATE TABLE IF NOT EXISTS user_recent_stats (
    id               INTEGER      PRIMARY KEY,

    ship_id          INT          NOT NULL,                   -- 船只ID
    mode             TEXT         NOT NULL,                   -- 战斗模式

    battles          INT          DEFAULT 0,                  -- 战斗场次变化
    wins             INT          DEFAULT 0,                  -- 胜利场次变化
    losses           INT          DEFAULT 0,                  -- 失败场次变化
    damage           INT          DEFAULT 0,                  -- 造成伤害变化
    frags            INT          DEFAULT 0,                  -- 击毁数变化
    original_exp     INT          DEFAULT 0,                  -- 原始经验变化
    scouting_damage  INT          DEFAULT 0,                  -- 侦查伤害变化
    art_agro         INT          DEFAULT 0,                  -- 潜在伤害变化
    planes_killed    INT          DEFAULT 0,                  -- 击落飞机变化
    survived         INT          DEFAULT 0,                  -- 存活场次
    hit_rate         REAL         DEFAULT 0,                  -- 主炮命中率 (hits / shots)

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- 为时间范围查询建立索引
CREATE INDEX idx_create_time ON user_recent_stats(created_at);