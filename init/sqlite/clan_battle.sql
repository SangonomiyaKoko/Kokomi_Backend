-- 公会战赛季对战明细表
-- 每个赛季对应一个独立的 SQLite 数据库文件（season_{season_id}.db），文件内仅含本表
-- 字段与原有 MySQL 分表 S_clan_battle_{season_id} 一一对应
CREATE TABLE clan_battle (
    id               INTEGER      PRIMARY KEY AUTOINCREMENT,

    clan_id          INTEGER      NOT NULL,        -- 公会 ID
    team_number      INTEGER      NOT NULL,        -- 队伍编号（1 或 2）

    victory          INTEGER      NOT NULL,        -- 1=胜 0=负
    result           TEXT         NOT NULL,        -- 战斗结果（分数变动/晋级or保级赛进度/升降级）

    -- 战斗结束时的队伍数据
    rating           INTEGER      NOT NULL,        -- 公开评分
    league           INTEGER      NOT NULL,        -- 联赛等级（0/1/2/3/4）
    division         INTEGER      NOT NULL,        -- 分段（1/2/3）
    division_rating  INTEGER      NOT NULL,        -- 分段评分
    stage_type       INTEGER      DEFAULT NULL,    -- 晋级赛类型（1=晋级 2=保级，非晋级赛为 NULL）
    stage_progress   TEXT         DEFAULT NULL,    -- 晋级赛进度（★☆ 串）

    time_window      INTEGER      DEFAULT NULL,    -- 战斗所处时间区间索引（1/2/3，窗口外为 NULL）
    battle_time      INTEGER      NOT NULL,        -- 战斗时间戳（Unix 秒）

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_time ON clan_battle (battle_time);
CREATE INDEX idx_cid ON clan_battle (clan_id);

CREATE TABLE database_meta (
    id               INTEGER      PRIMARY KEY AUTOINCREMENT,

    metric_key       TEXT         UNIQUE,
    metric_value     INTEGER      DEFAULT 0,

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO database_meta (metric_key) VALUES ('total');
INSERT INTO database_meta (metric_key) VALUES ('record');
INSERT INTO database_meta (metric_key) VALUES ('discard');