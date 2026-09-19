-- 公会基础信息表
-- 存储公会的基本信息，包括标签和段位
CREATE TABLE IF NOT EXISTS T_clan_base (
    id               INT          AUTO_INCREMENT,

    clan_id          BIGINT       NOT NULL,        -- 10位的非连续数字
    tag              VARCHAR(10)  NOT NULL,        -- 公会标签
    league           TINYINT      DEFAULT 5,       -- 当前段位 0紫金 1白金 2黄金 3白银 4青铜 5无

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_cid (clan_id)
);

-- 公会统计表
-- 存储公会的赛季战斗统计数据
CREATE TABLE IF NOT EXISTS T_clan_stats (
    id               INT          AUTO_INCREMENT,

    clan_id          BIGINT       NOT NULL,        -- 10位的非连续数字
    season           TINYINT      DEFAULT 0,       -- 赛季 ID
    leading_team     TINYINT      DEFAULT NULL,    -- 主力队伍编号
    battles          INT          DEFAULT 0,       -- 战斗总数
    win_rate         FLOAT        DEFAULT 0,       -- 胜率
    public_rating    FLOAT        DEFAULT 1100,    -- 公开评分
    league           TINYINT      DEFAULT 4,       -- 段位 0紫金 1白金 2黄金 3白银 4青铜
    division         TINYINT      DEFAULT 2,       -- 分段 1/2/3
    division_rating  INT          DEFAULT 0,       -- 分段评分
    max_streak       INT          DEFAULT 0,       -- 最长连胜
    stage_type       TINYINT      DEFAULT NULL,    -- 晋级赛类型
    stage_progress   VARCHAR(5)   DEFAULT NULL,    -- 晋级赛进度
    last_battle_at   TIMESTAMP    DEFAULT NULL,    -- 最后战斗时间

    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE KEY uk_cid (clan_id),

    INDEX idx_last_battle (last_battle_at)
);

-- 公会队伍表
-- 存储公会当前赛季的两支队伍数据，与 T_clan_base 按 clan_id 一一对应
CREATE TABLE IF NOT EXISTS T_clan_team (
    id               INT          AUTO_INCREMENT,

    clan_id          BIGINT       NOT NULL,        -- 10位的非连续数字
    season           TINYINT      DEFAULT 0,       -- 赛季 ID
    team_alpha       JSON         DEFAULT NULL,    -- 队伍数据 JSON
    team_bravo       JSON         DEFAULT NULL,    -- 队伍数据 JSON

    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE KEY uk_cid (clan_id)
);

-- 公会成员表
-- 存储公会成员数量和成员 ID 列表
CREATE TABLE IF NOT EXISTS T_clan_users (
    id               INT          AUTO_INCREMENT,

    clan_id          BIGINT       NOT NULL,        -- 10位的非连续数字
    is_enabled       BOOLEAN      DEFAULT TRUE,    -- 工会是否有效
    activity_level   TINYINT      DEFAULT 0,       -- 工会活跃等级
    member_count     INT          DEFAULT 0,       -- 成员数量
    member_ids       JSON         DEFAULT NULL,    -- 成员 ID 列表
    next_refresh_at  TIMESTAMP    DEFAULT NULL,    -- 最低下次更新时间

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_cid (clan_id)
);

-- 公会行为记录表
-- 记录成员加入和退出公会的历史，只追加不更新
CREATE TABLE IF NOT EXISTS T_clan_action (
    id               INT          AUTO_INCREMENT,

    clan_id          BIGINT       NOT NULL,        -- 10位的非连续数字
    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    action_type      TINYINT      NOT NULL,        -- 1=加入，2=退出

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    INDEX idx_cid (clan_id),
    INDEX idx_aid (account_id)
);

CREATE TABLE IF NOT EXISTS T_clan_activity (
    id               INT          AUTO_INCREMENT,

    clan_level       TINYINT      NOT NULL,        -- 工会活跃等级
    clan_count       INT          DEFAULT 0,       -- 工会数量

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_level (clan_level)
);