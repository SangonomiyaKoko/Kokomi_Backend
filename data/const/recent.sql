-- 用户每日摘要表
-- 每一个日期一行，记录当日快照的概要信息以及统计数据的索引
CREATE TABLE IF NOT EXISTS user_daily_summary (
    id               INTEGER      PRIMARY KEY,

    -- 快照日期
    snapshot_date    INT          UNIQUE,                     -- 格式：YYYYMMDD

    -- 标记用户是否公开战绩        
    -- 若标记为未公开战绩，则后续字段中仅 update_time 字段数据有效
    is_public        BOOLEAN      NOT NULL,

    -- 用户总战斗场次及指定模式战斗场次
    total_battles    INT          NOT NULL DEFAULT 0,         -- 总战斗场次
    pve_battles      INT          NOT NULL DEFAULT 0,         -- PvE 战斗场次
    pvp_battles      INT          NOT NULL DEFAULT 0,         -- PvP 战斗场次
    rank_battles     INT          NOT NULL DEFAULT 0,         -- Rank 战斗场次
    clan_battles     INT          NOT NULL DEFAULT 0,         -- Clan 战斗场次

    -- 其他数据
    karma            INT          NOT NULL DEFAULT 0,         -- 业力值

    -- 该船只下各指定模式战斗统计数据索引（指向 ship_index_map 表中对应行）
    -- 约定：NULL=未记录  0=已记录无数据  DATE=该模式最新快照
    pvp_index        INT          DEFAULT NULL,               -- PvP 战斗数据索引
    rank_index       INT          DEFAULT NULL,               -- Rank 战斗数据索引
    clan_index       INT          DEFAULT NULL,               -- Clan 战斗数据索引

    -- 该快照数据的更新时间戳
    update_time      INT          NOT NULL,

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);


-- 最新船只快照缓存表
-- 记录每艘船最新一次快照的索引及基础战斗数，用于更新时获取本地缓存数据
CREATE TABLE IF NOT EXISTS ship_latest_index (
    id               INTEGER      PRIMARY KEY,

    -- 船只 ID
    ship_id          INT          UNIQUE,
    
    -- 该船只下各指定模式战斗场次
    pvp_battles      INT          NOT NULL DEFAULT 0,         -- PvP 战斗场次
    pvp_index        INT          DEFAULT NULL,               -- PvP 战斗数据索引
    rank_battles     INT          NOT NULL DEFAULT 0,         -- Rank 战斗场次
    rank_index       INT          DEFAULT NULL,               -- Rank 战斗数据索引
    clan_battles     INT          NOT NULL DEFAULT 0,         -- Clan 战斗场次
    clan_index       INT          DEFAULT NULL,               -- Clan 战斗数据索引

    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);

-- 特殊行说明：
-- 记录各模式下最新索引，更新时也通过它对比上次缓存的最新数据（如 total_battles 是否变化）判断是否需要更新
-- ⚠️注意：特殊行的 index 指向 map 层；普通船只行的 index 指向 data 层
INSERT OR IGNORE INTO ship_latest_index (ship_id) VALUES (1000000000);  -- 1000000000 已确保不可能是真实 ship_id，便于区分


-- 船只快照数据映射表
-- 将一个日期下指定模式的所有船只快照索引打包压缩储存
CREATE TABLE IF NOT EXISTS ship_index_map (
    id               INTEGER      PRIMARY KEY,

    -- 数据索引（mode + index）
    ship_mode        INT          NOT NULL,                   -- 战斗模式，约定：1-pvp 2-rank 3-clan
    ship_index       INT          NOT NULL,                   -- 快照索引，格式：YYYYMMDD

    -- 数据基本信息
    ships            INT          NOT NULL DEFAULT 0,         -- 总船只数
    battles          INT          NOT NULL DEFAULT 0,         -- 总战斗场次
    wins             INT          NOT NULL DEFAULT 0,         -- 总胜场
    damage           INT          NOT NULL DEFAULT 0,         -- 总伤害
    frags            INT          NOT NULL DEFAULT 0,         -- 总击毁数
    exp              INT          NOT NULL DEFAULT 0,         -- 总经验值

    -- 记录所有船只及其对应的快照数据索引
    index_map        TEXT         DEFAULT NULL,               -- 船只索引合集

    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    
    UNIQUE(ship_mode, ship_index)
);


-- 船只单日快照数据表
-- 存储一条指定模式下单船只的战绩快照，是数据最小粒度
CREATE TABLE IF NOT EXISTS ship_index_data (
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

    updated_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(ship_mode, ship_id, ship_index),
    CHECK(ship_mode IN (1, 2, 3))
);


-- 用户近期详细数据统计表
-- 每条记录对应一艘船的某个战斗模式的各项战绩变化量
CREATE TABLE IF NOT EXISTS user_recent_stats (
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