-- 游戏版本近期数据表
-- 每个游戏版本对应一个独立的 SQLite 数据库文件（data/version/{version}.db），文件内仅含本表
-- 按船只聚合本版本内的战斗增量，由 cache_v2 在刷新用户数据时累加写入
CREATE TABLE ship_recent_stats (
    id               INTEGER      PRIMARY KEY AUTOINCREMENT,

    ship_id          INTEGER      NOT NULL UNIQUE, -- 1-11位的非连续数字
    battles          INTEGER      NOT NULL DEFAULT 0,  -- 本版本新增场次
    wins             INTEGER      NOT NULL DEFAULT 0,  -- 本版本新增胜场
    damage           INTEGER      NOT NULL DEFAULT 0,  -- 本版本新增伤害
    frags            INTEGER      NOT NULL DEFAULT 0,  -- 本版本新增击毁
    exp              INTEGER      NOT NULL DEFAULT 0,  -- 本版本新增经验
    survived         INTEGER      NOT NULL DEFAULT 0,  -- 本版本新增存活场次
    scouting_damage  INTEGER      NOT NULL DEFAULT 0,  -- 本版本新增侦查伤害
    potential_damage INTEGER      NOT NULL DEFAULT 0,  -- 本版本新增潜在伤害

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP,
    updated_at       DATETIME     DEFAULT NULL
);
