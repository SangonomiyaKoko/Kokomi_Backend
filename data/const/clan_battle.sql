-- 公会战赛季对战明细表
-- 每个赛季对应一个独立的 SQLite 数据库文件（season_{season_id}.db），文件内仅含本表
CREATE TABLE IF NOT EXISTS clan_battle (
    id               INTEGER      PRIMARY KEY AUTOINCREMENT,

    clan_id          INTEGER      NOT NULL,        -- 公会 ID
    team_number      INTEGER      NOT NULL,        -- 队伍编号（1 或 2）
    
    battle_result    INTEGER      NOT NULL,        -- 战斗结果（1=胜 0=负）
    battle_rating    TEXT         DEFAULT NULL,    -- 战斗评分变化（如 +5 / -3，无变化为 NULL）
    league           INTEGER      DEFAULT NULL,    -- 联赛等级（0/1/2/3/4）
    division         INTEGER      DEFAULT NULL,    -- 分段（1/2/3）
    division_rating  INTEGER      DEFAULT NULL,    -- 分段评分
    public_rating    INTEGER      DEFAULT NULL,    -- 公开评分
    stage_type       INTEGER      DEFAULT NULL,    -- 晋级赛类型（1=晋级 2=保级，非晋级赛为 NULL）

    battle_time      INTEGER      NOT NULL,        -- 战斗时间戳（Unix 秒）

    created_at       DATETIME     DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_time ON clan_battle (battle_time);
CREATE INDEX IF NOT EXISTS idx_cid ON clan_battle (clan_id);
