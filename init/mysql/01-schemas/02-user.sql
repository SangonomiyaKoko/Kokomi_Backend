-- 用户基础信息表
-- 存储用户的基本信息，包括用户名、注册时间等
CREATE TABLE IF NOT EXISTS T_user_base (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    username         VARCHAR(25)  NOT NULL,        -- 最大25个字符
    register_time    TIMESTAMP    DEFAULT NULL,    -- 注册时间
    insignias        VARCHAR(55)  DEFAULT NULL,    -- 徽章信息

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id)
);

-- 用户统计表
-- 存储用户的活跃度和战斗统计数据
CREATE TABLE IF NOT EXISTS T_user_stats (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    is_enabled       BOOLEAN      DEFAULT TRUE,    -- 用户是否有效
    is_public        BOOLEAN      DEFAULT TRUE,    -- 用户是否公开战绩
    activity_level   TINYINT      DEFAULT 0,       -- 用户活跃等级
    total_battles    INT          DEFAULT 0,       -- 总战斗场次
    pve_battles      INT          DEFAULT 0,       -- PvE 场次
    pvp_battles      INT          DEFAULT 0,       -- PvP 场次
    ranked_battles   INT          DEFAULT 0,       -- 排位战场次
    rating_battles   INT          DEFAULT 0,       -- 评分战场次
    karma            INT          DEFAULT 0,       -- 业力值
    last_battle_at   TIMESTAMP    DEFAULT NULL,    -- 最后战斗时间
    next_refresh_at  TIMESTAMP    DEFAULT NULL,    -- 最低下次更新时间

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id)
);

-- 用户行为记录表
-- 记录用户改名等历史行为，只追加不更新
CREATE TABLE IF NOT EXISTS T_user_action (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    username         VARCHAR(25)  NOT NULL,        -- 曾用名

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    INDEX idx_aid (account_id),
    INDEX idx_username (username)
);

-- 用户公会关联表
-- 记录用户当前所属公会，一个用户只能属于一个公会
CREATE TABLE IF NOT EXISTS T_user_clan (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-10位的非连续数字
    clan_id          BIGINT       DEFAULT NULL,    -- 10位的非连续数字，NULL 表示无公会

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id),
    INDEX idx_cid (clan_id)
);

-- 用户 PvP 信息表
-- 存储用户的 PvP 基本战斗数据
CREATE TABLE IF NOT EXISTS T_user_random (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    battles          INT          DEFAULT 0,       -- 总战斗场次
    total_exp        BIGINT       DEFAULT 0,
    win_rate         FLOAT        DEFAULT 0,       -- 胜率
    avg_damage       INT          DEFAULT 0,       -- 场均伤害
    avg_frags        FLOAT        DEFAULT 0,       -- 场均击毁
    avg_exp          INT          DEFAULT 0,       -- 场均经验
    max_exp          INT          DEFAULT 0,
    max_frags        INT          DEFAULT 0,
    max_planes       INT          DEFAULT 0,
    max_damage       INT          DEFAULT 0,
    max_scouting     INT          DEFAULT 0,
    max_potential    INT          DEFAULT 0,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id)
);

-- 用户 Rank 信息表
-- 存储用户的 Rank 基本战斗数据
CREATE TABLE IF NOT EXISTS T_user_ranked (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    battles          INT          DEFAULT 0,       -- 总战斗场次
    total_exp        BIGINT       DEFAULT 0,
    win_rate         FLOAT        DEFAULT 0,       -- 胜率
    avg_damage       INT          DEFAULT 0,       -- 场均伤害
    avg_frags        FLOAT        DEFAULT 0,       -- 场均击毁
    avg_exp          INT          DEFAULT 0,       -- 场均经验
    max_exp          INT          DEFAULT 0,
    max_frags        INT          DEFAULT 0,
    max_planes       INT          DEFAULT 0,
    max_damage       INT          DEFAULT 0,
    max_scouting     INT          DEFAULT 0,
    max_potential    INT          DEFAULT 0,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id)
);


CREATE TABLE IF NOT EXISTS T_user_cache (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    is_due           BOOLEAN      DEFAULT FALSE,
    ships            INT          DEFAULT 0,
    cache            JSON         DEFAULT NULL,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id),

    UNIQUE INDEX idx_due_aid (is_due, account_id)
);

-- 储存用户所有船只数据
CREATE TABLE IF NOT EXISTS T_user_ships (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,        -- 1-11位的非连续数字
    user_level       TINYINT      DEFAULT 0,       -- 标记用户水平，为 0 表示数据过少无法评分
    ship_count       INT          DEFAULT 0,       -- payload 中船只数量
    payload          BLOB         DEFAULT NULL,    -- 压缩后的船只数据

    -- 用于标记用户待更新的时间戳，为 0 表示不需要更新, > 0 表示需要更新
    -- 程序读取所有需要更新用户的 pending_at 值并按从早到晚的优先级顺序更新
    pending_at       INT          DEFAULT 0,

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id),

    INDEX idx_pending_aid (pending_at, account_id)
);

-- 用户配置表
-- 存储用户的个性化配置，如等级、存储限制等
CREATE TABLE IF NOT EXISTS T_user_config (
    id               INT          AUTO_INCREMENT,

    account_id       BIGINT       NOT NULL,
    user_level       TINYINT      DEFAULT 0,       -- 用户等级 0无 1普通 2高级
    storage_limit    INT          DEFAULT 0,       -- Recent 功能储存数据限制
    query_count      INT          DEFAULT 0,       -- 账号查询次数
    last_query_at    TIMESTAMP    DEFAULT NULL,    -- 上次查询时间

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_aid (account_id),
    

    UNIQUE INDEX idx_level_and_aid (user_level, account_id)
);

CREATE TABLE IF NOT EXISTS T_user_activity (
    id               INT          AUTO_INCREMENT,

    user_level       TINYINT      NOT NULL,        -- 用户活跃等级
    user_count       INT          DEFAULT 0,       -- 用户数量

    created_at       TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id),

    UNIQUE INDEX idx_level (user_level)
);


-- 后续新增关联表的初始化sql语句，user/clan也类似
-- INSERT INTO new_table (account_id)
-- SELECT account_id
-- FROM T_user_base
-- ORDER BY id ASC;