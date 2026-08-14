-- 公会战赛季对战明细表
-- 每个赛季对应一个独立的 SQLite 数据库文件（season_{season_id}.db），文件内仅含本表
CREATE TABLE IF NOT EXISTS clan_battle (
    id               INTEGER      PRIMARY KEY AUTOINCREMENT,

    -- 战斗时间戳（Unix 秒）
    battle_time      INTEGER      NOT NULL,

    -- 公会 ID
    clan_id          INTEGER      NOT NULL,

    -- 队伍编号（1 或 2）
    team_number      INTEGER      NOT NULL,

    -- 战斗结果（1=胜 0=负）
    battle_result    INTEGER      NOT NULL,

    -- 战斗评分变化（如 +5 / -3，无变化为 NULL）
    battle_rating    TEXT         DEFAULT NULL,

    -- 晋级赛阶段标识（如 +★）
    battle_stage     TEXT         DEFAULT NULL,

    -- 联赛等级
    league           INTEGER      DEFAULT NULL,

    -- 分段
    division         INTEGER      DEFAULT NULL,

    -- 分段评分
    division_rating  INTEGER      DEFAULT NULL,

    -- 公开评分
    public_rating    INTEGER      DEFAULT NULL,

    -- 晋级赛类型（1=晋级 2=保级）
    stage_type       INTEGER      DEFAULT NULL,

    -- 晋级赛进度（如 ★★☆）
    stage_progress   TEXT         DEFAULT NULL,

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time ON clan_battle (battle_time);
CREATE INDEX IF NOT EXISTS idx_cid ON clan_battle (clan_id);
