-- 用户每日摘要表
-- 每一个日期一行，记录当日快照的概要信息以及统计数据的索引
CREATE TABLE user_daily_summary (
    id               INTEGER      PRIMARY KEY,

    snapshot_date    INT          UNIQUE,                     -- 快照日期，格式：YYYYMMDD

    -- 标记用户是否公开战绩        
    -- 若标记为未公开战绩，则后续字段中仅 update_time 字段数据有效
    is_public        BOOLEAN      NOT NULL,

    -- 用户总战斗场次及指定模式战斗场次
    total_battles    INT          NOT NULL DEFAULT 0,         -- 总战斗场次
    pve_battles      INT          NOT NULL DEFAULT 0,         -- PvE 战斗场次
    pvp_battles      INT          NOT NULL DEFAULT 0,         -- PvP 战斗场次
    rank_battles     INT          NOT NULL DEFAULT 0,         -- Rank 战斗场次
    clan_battles     INT          NOT NULL DEFAULT 0,         -- Clan 战斗场次
    karma            INT          NOT NULL DEFAULT 0,         -- 业力值

    -- 各指定模式战斗统计数据索引，指向 ship_index_map 表中对应行
    -- 约定：NULL=未记录  0=无统计数据  DATE=该模式所指向的快照
    pvp_index        INT          DEFAULT NULL,               -- PvP 战斗数据索引
    rank_index       INT          DEFAULT NULL,               -- Rank 战斗数据索引
    clan_index       INT          DEFAULT NULL,               -- Clan 战斗数据索引

    update_time      INT          NOT NULL,                   -- 该快照数据的更新时间戳

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- 各模式最新快照表
-- 记录每艘船最新一次快照的索引及基础战斗数，用于更新时获取本地缓存数据
CREATE TABLE mode_latest_index (
    id               INTEGER      PRIMARY KEY,

    ship_mode        INT          UNIQUE,                   -- 战斗模式，约定：1-pvp 2-rank 3-clan
    
    -- 该模式下战斗总体统计数据概览
    battles          INT          NOT NULL DEFAULT 0,         -- 总场次
    win_rate         REAL         NOT NULL DEFAULT 0.0,       -- 胜率
    avg_damage       INT          NOT NULL DEFAULT 0,         -- 场均伤害
    avg_frags        REAL         NOT NULL DEFAULT 0.0,       -- 场均击杀
    avg_exp          INT          NOT NULL DEFAULT 0.0,       -- 场均经验

    -- 该模式下战斗统计数据索引，指向 ship_index_map 表中对应行
    mode_index       INT          DEFAULT NULL,      -- 格式：YYYYMMDD

    update_time      INT          DEFAULT NULL,      -- 该快照数据的更新时间戳

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,

    CHECK(ship_mode IN (1, 2, 3))
);
INSERT INTO mode_latest_index (ship_mode) VALUES (1);
INSERT INTO mode_latest_index (ship_mode) VALUES (2);
INSERT INTO mode_latest_index (ship_mode) VALUES (3);

-- 最新船只快照缓存表
-- 记录每艘船最新一次快照的索引及基础战斗数，用于更新时获取本地缓存数据
CREATE TABLE ship_latest_index (
    id               INTEGER      PRIMARY KEY,

    ship_id          INT          NOT NULL,                   -- 船只 ID
    ship_mode        INT          NOT NULL,                   -- 战斗模式，约定：1-pvp 2-rank 3-clan
    
    -- 该模式下指定船只战斗总体统计数据概览
    battles          INT          NOT NULL DEFAULT 0,         -- 总场次
    win_rate         REAL         NOT NULL DEFAULT 0.0,       -- 胜率
    avg_damage       INT          NOT NULL DEFAULT 0,         -- 场均伤害
    avg_frags        REAL         NOT NULL DEFAULT 0.0,       -- 场均击杀
    avg_exp          INT          NOT NULL DEFAULT 0.0,       -- 场均经验
    
    -- 该模式下指定船只战斗统计数据索引，指向 ship_index_data 表中对应行
    data_index       INT          NOT NULL DEFAULT NULL,      -- 格式：YYYYMMDD

    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ship_mode, ship_id),

    CHECK(ship_mode IN (1, 2, 3))
);


-- 船只快照数据映射表
-- 将一个日期下指定模式的所有船只快照索引打包压缩储存
CREATE TABLE ship_index_map (
    id               INTEGER      PRIMARY KEY,

    -- 数据索引（mode + index）
    ship_mode        INT          NOT NULL,                   -- 战斗模式，约定：1-pvp 2-rank 3-clan
    ship_index       INT          NOT NULL,                   -- 快照索引，格式：YYYYMMDD

    -- 数据基本信息
    ships            INT          NOT NULL DEFAULT 0,         -- 总船只数
    battles          INT          NOT NULL DEFAULT 0,         -- 总场次
    wins             INT          NOT NULL DEFAULT 0,         -- 总胜场
    damage           INT          NOT NULL DEFAULT 0,         -- 总伤害
    frags            INT          NOT NULL DEFAULT 0,         -- 总击杀
    exp              INT          NOT NULL DEFAULT 0,         -- 总经验

    -- 记录所有船只及其对应的快照数据索引
    index_map        TEXT         DEFAULT NULL,               -- 字符串格式：ship_id:index,...

    update_time      INT          DEFAULT NULL,               -- 该快照数据的更新时间戳

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ship_mode, ship_index),

    CHECK(ship_mode IN (1, 2, 3))
);


-- 船只单日快照数据表
-- 存储一条指定模式下单船只的战绩快照，是数据最小粒度
CREATE TABLE ship_index_data (
    id               INTEGER      PRIMARY KEY,

    -- 数据索引（mode + id + index）
    ship_id          INT          NOT NULL,                    -- 船只ID
    ship_mode        INT          NOT NULL,                    -- 战斗模式，约定：1-pvp 2-rank 3-clan
    ship_index       INT          NOT NULL,                    -- 快照索引，格式：YYYYMMDD

    -- 统计数据，不同的模式对应的可选数据类型如下
    -- random:      solo  div2  div3
    -- ranked:      solo  \     \
    -- clan(wg):    \     div   \
    -- clan(lesta): solo  div   \
    data_type_1      TEXT         DEFAULT NULL,                -- 数据类型1，solo
    data_type_2      TEXT         DEFAULT NULL,                -- 数据类型2，div2/div
    data_type_3      TEXT         DEFAULT NULL,                -- 数据类型3，div3

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ship_mode, ship_id, ship_index),

    CHECK(ship_mode IN (1, 2, 3))
);


-- 用户近期详细数据统计表
-- 每条记录对应一艘船的某个战斗模式的各项战绩变化量
CREATE TABLE user_recent_stats (
    id               INTEGER      PRIMARY KEY,

    ship_id          INT          NOT NULL,                   -- 船只ID

    -- 数据类型（mode + type）
    data_mode        INT          NOT NULL,                   -- 战斗模式，约定：1-pvp 2-rank 3-clan
    data_type        INT          NOT NULL,                   -- 数据类型，约定：1-solo 2-div2/div 3-div3

    -- 近期数据
    battles          INT          DEFAULT 0,                  -- 战斗场次
    wins             INT          DEFAULT 0,                  -- 胜利场次
    losses           INT          DEFAULT 0,                  -- 失败场次
    damage           INT          DEFAULT 0,                  -- 伤害
    planes           INT          DEFAULT 0,                  -- 击落飞机
    frags            INT          DEFAULT 0,                  -- 击毁数
    exp              INT          DEFAULT 0,                  -- 经验值
    survived         INT          DEFAULT 0,                  -- 存活场次
    scout_damage     INT          DEFAULT 0,                  -- 侦查伤害
    art_agro         INT          DEFAULT 0,                  -- 潜在伤害
    hit_rate         REAL         DEFAULT 0,                  -- 主炮命中率 (hits / shots)

    -- 该条数据对应的战斗结束时间戳
    battle_time      INT          NOT NULL,

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,

    CHECK(data_mode IN (1, 2, 3)),
    CHECK(data_type IN (1, 2, 3))
);

-- 为时间范围查询建立索引
CREATE INDEX idx_battle_time ON user_recent_stats(battle_time);