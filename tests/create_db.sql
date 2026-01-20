CREATE DATABASE IF NOT EXISTS game_test;
USE game_test;

SET GLOBAL TRANSACTION ISOLATION LEVEL READ COMMITTED;

CREATE TABLE region (
    id               INT          PRIMARY KEY,
    name             VARCHAR(5)  NOT NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT INTO region 
    (id, name) 
VALUES
    (1, 'asia'),
    (2, 'eu'),
    (3, 'na'),
    (4, 'ru'),
    (5, 'cn');


CREATE TABLE platform (
    id               INT          PRIMARY KEY,
    name             VARCHAR(10)  NOT NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

INSERT INTO platform 
    (id, name) 
VALUES
    (1, 'qq_bot'),
    (2, 'qq_group'),
    (3, 'qq_guild'),
    (4, 'discord');

CREATE TABLE region_version (
    id             INT            AUTO_INCREMENT,
    region_id      TINYINT        NOT NULL,
    short_version  VARCHAR(10)    NOT NULL,
    full_version   VARCHAR(100)   NOT NULL,
    version_start  TIMESTAMP      NOT NULL,
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    INDEX idx_region_id (region_id) -- 索引
);

INSERT INTO region_version
    (region_id, short_version, full_version, version_start)
VALUES
    (1, '14.11', '14.11.0.post2/ef08cd31b41e488c3b3669ef3624cd62d73f1d27', CURRENT_TIMESTAMP), 
    (2, '14.11', '14.11.0.post3/83a28b8913164eb612d022bd9c69c398de66bfb5', CURRENT_TIMESTAMP), 
    (3, '14.11', '14.11.0.post1/2f3e7195c1bb2050de4cb206814e6a11309a2f67', CURRENT_TIMESTAMP), 
    (4, '25.12', '25.12.0.post4/08ec98b7a1fea2baa7281561d48d5bc76a36c05b', CURRENT_TIMESTAMP), 
    (5, '14.11', '14.11.0.post4/de23d92ec3bde0ee2ba1cd5dabfee5d670bdef8e', CURRENT_TIMESTAMP);

CREATE TABLE user_base (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    region_id        TINYINT      NOT NULL,
    account_id       BIGINT       NOT NULL UNIQUE,    -- 1-11位的非连续数字
    -- 用户基础信息数据: name
    username         VARCHAR(25)  NOT NULL,    -- 最大25个字符，编码：utf-8
    register_time    TIMESTAMP    DEFAULT NULL,
    insignias        VARCHAR(55)  DEFAULT NULL,
    -- 记录数据创建的时间和更新时间
    touch_at         TIMESTAMP    DEFAULT NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    INDEX idx_username (username), -- 索引

    UNIQUE INDEX idx_rid_aid (region_id, account_id) -- 索引
);

CREATE TABLE clan_base (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    region_id        TINYINT      NOT NULL,
    clan_id          BIGINT       NOT NULL UNIQUE,     -- 11位的非连续数字
    -- 工会基础信息数据: tag league
    tag              VARCHAR(10)  NOT NULL,     -- 最大5个字符，编码：utf-8
    league           TINYINT      DEFAULT 5,    -- 当前段位 0紫金 1白金 2黄金 3白银 4青铜 5无
    -- 记录数据创建的时间和更新时间
    touch_at         TIMESTAMP    DEFAULT NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    INDEX idx_tag (tag), -- 索引

    UNIQUE INDEX idx_rid_cid (region_id, clan_id) -- 索引
);

CREATE TABLE user_stats (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    account_id       BIGINT       NOT NULL,     -- 1-11位的非连续数字
    -- 关于用户活跃的信息，用于recent/recents/用户排行榜功能
    is_enabled       TINYINT      DEFAULT 0,    -- 用于标记用户的有效性，0表示无效，1表示有效
    activity_level   TINYINT      DEFAULT 0,    -- 人为设置的用户活跃的等级
    is_public        TINYINT      DEFAULT 0,    -- 用户是否隐藏战绩，0表示隐藏，1表示公开
    total_battles    INT          DEFAULT 0,    -- 用户总场次
    pvp_battles      INT          DEFAULT 0,    -- 用户随机总场次
    ranked_battles   INT          DEFAULT 0,    -- 用户排位总场次
    last_battle_at   TIMESTAMP    DEFAULT NULL, -- 用户最后战斗时间
    -- 记录数据创建的时间和更新时间
    touch_at         TIMESTAMP    DEFAULT NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_aid (account_id), -- 索引

    FOREIGN KEY (account_id) REFERENCES user_base(account_id) ON DELETE CASCADE -- 外键
);


CREATE TABLE user_clan (
    id               INT          AUTO_INCREMENT,
    account_id       BIGINT       NOT NULL,       -- 1-10位的非连续数字
    clan_id          BIGINT       DEFAULT NULL,   -- 10位的非连续数字 none表示无工会
    -- 记录数据创建的时间和更新时间
    touch_at         TIMESTAMP    DEFAULT NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_aid (account_id), -- 唯一索引

    INDEX idx_cid (clan_id), -- 非唯一索引

    FOREIGN KEY (account_id) REFERENCES user_base(account_id) ON DELETE CASCADE, -- 外键
    FOREIGN KEY (clan_id) REFERENCES clan_base(clan_id) ON DELETE CASCADE -- 外键
);

CREATE TABLE bind_idx (
    id               INT          AUTO_INCREMENT,
    platform_id      INT          NOT NULL,
    platform_user_id VARCHAR(64)  NOT NULL,

    current_id       INT          DEFAULT NULL,
    premium_expired_at TIMESTAMP  DEFAULT NULL,
    premium_level    INT          DEFAULT 0,
    premium_limit    INT          DEFAULT 0,

    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_platform_user (platform_id, platform_user_id)
);

CREATE TABLE bind_list (
    id               INT          AUTO_INCREMENT,
    user_id          INT          NOT NULL,
    game_id          INT          NOT NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_user_game (user_id, game_id),

    FOREIGN KEY (user_id) REFERENCES bind_idx(id) ON DELETE CASCADE, -- 外键
    FOREIGN KEY (game_id) REFERENCES user_base(id) ON DELETE CASCADE -- 外键
);

CREATE TABLE user_cache (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    account_id       BIGINT       NOT NULL,     -- 1-11位的非连续数字
    -- 记录用户缓存的数据和更新时间
    pvp_count        INT          DEFAULT 0, -- 总战斗场次
    win_rate         DOUBLE       DEFAULT 0, -- 胜率
    avg_damage       DOUBLE       DEFAULT 0, -- 场均
    avg_frags        DOUBLE       DEFAULT 0, -- 击杀
    max_damage       INT          DEFAULT 0, -- 个人最高伤害
    max_damage_id    BIGINT       DEFAULT NULL, -- 个人最高伤害对应的船只
    max_exp          INT          DEFAULT 0, -- 个人最高经验
    max_exp_id       BIGINT       DEFAULT NULL, -- 个人最高经验对应的船只
    cache            BLOB         DEFAULT NULL, -- 压缩处理后的缓存数据
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    DEFAULT NULL ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_aid (account_id), -- 索引

    FOREIGN KEY (account_id) REFERENCES user_base(account_id) ON DELETE CASCADE -- 外键
);

CREATE TABLE recent (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    region_id        TINYINT      NOT NULL,
    account_id       BIGINT       NOT NULL,
    -- 用户配置
    enable_recent    TINYINT      DEFAULT 0,      -- 是否启用recent功能
    enable_daily     TINYINT      DEFAULT 0,      -- 是否启用recents功能
    recent_limit     INT          DEFAULT 0,      -- recent功能储存数据上限
    last_query_at    TIMESTAMP    DEFAULT NULL,   -- 用户上次查询的时间
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_rid_aid (region_id, account_id) -- 索引

    FOREIGN KEY (region_id, account_id) REFERENCES user_base(region_id, account_id) ON DELETE CASCADE -- 外键
);

CREATE TABLE recent_pro (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    user_id          INT          NOT NULL,
    game_id          INT          NOT NULL,
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    INDEX idx_user (user_id),
    INDEX idx_game (game_id),

    FOREIGN KEY (user_id) REFERENCES bind_idx(id) ON DELETE CASCADE -- 外键
);

CREATE TABLE clan_stats (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    clan_id          BIGINT       NOT NULL,     -- 10位的非连续数字
    -- 关于工会活跃的信息，用于工会排行榜功能
    is_active        TINYINT      DEFAULT 0,    -- 用于标记工会的有效性，0表示无效，1表示有效
    season           TINYINT      DEFAULT 0,    -- 当前赛季代码 1-30+
    public_rating    INT          DEFAULT 1100, -- 工会评分 1199 - 3000+  1100表示无数据
    league           TINYINT      DEFAULT 4,    -- 段位 0紫金 1白金 2黄金 3白银 4青铜
    division         TINYINT      DEFAULT 2,    -- 分段 1 2 3
    division_rating  INT          DEFAULT 0,    -- 分段分数，示例：白金 1段 25分
    last_battle_at   TIMESTAMP    DEFAULT NULL, -- 上次战斗结束时间，用于判断是否有更新数据
    team_data        VARCHAR(100) DEFAULT NULL, -- 小队数据
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_cid (clan_id), -- 索引

    FOREIGN KEY (clan_id) REFERENCES clan_base(clan_id) ON DELETE CASCADE -- 外键
);

CREATE TABLE activation_codes (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    -- 激活码相关信息
    code             VARCHAR(20)  NOT NULL,    -- 激活码
    max_use          INT          NOT NULL,    -- 最多使用次数
    used_count       INT          NOT NULL,    -- 已使用次数
    validity         INT          NOT NULL,    -- 有效期(Days)
    premium_level    INT          NOT NULL,    -- 绑定账号限制
    recent_limit     INT          NOT NULL,    -- 限制
    code_describe    VARCHAR(50)  DEFAULT NULL,-- 备注
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_code (code) -- 索引
);

CREATE TABLE user_activation (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    -- 激活码相关信息
    code             VARCHAR(20)  NOT NULL,    -- 激活码
    user_id          INT          NOT NULL,    -- 用户id
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (id), -- 主键

    UNIQUE INDEX idx_code_user (code, user_id), -- 索引

    FOREIGN KEY (user_id) REFERENCES bind_idx(id) ON DELETE CASCADE, -- 外键
    FOREIGN KEY (code) REFERENCES activation_codes(code) ON DELETE CASCADE -- 外键
);

CREATE TABLE clan_battle_s32 (
    -- 相关id
    id               INT          AUTO_INCREMENT,
    -- 对局相关信息和ID
    battle_time      TIMESTAMP    NOT NULL,     -- 战斗时间
    region_id        TINYINT      NOT NULL,     -- 服务器id
    clan_id          BIGINT       NOT NULL,     -- 10位的非连续数字
    team_number      TINYINT      NOT NULL,     -- 队伍id
    -- 对局结果
    battle_result    VARCHAR(10)  NOT NULL,     -- 对局结果 胜利或者失败
    battle_rating    VARCHAR(10)  DEFAULT NULL, -- 对局分数 如果是晋级赛则会显示为0
    battle_stage     VARCHAR(10)  DEFAULT NULL, -- 对局结果 仅对于stage有效
    -- 对局结算的数据
    league           TINYINT      DEFAULT NULL, -- 段位 0紫金 1白金 2黄金 3白银 4青铜
    division         TINYINT      DEFAULT NULL, -- 分段 1 2 3
    division_rating  INT          DEFAULT NULL, -- 分段分数，示例：白金 1段 25分
    public_rating    INT          DEFAULT NULL, -- 工会评分 1199 - 3000
    stage_type       VARCHAR(10)  DEFAULT NULL, -- 晋级赛/保级赛 默认为Null
    stage_progress   VARCHAR(50)  DEFAULT NULL, -- 晋级赛/保级赛的当前结果
    -- 记录数据创建的时间和更新时间
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- 因为数据不会更新，所以不需要updated_at，只需要created_at

    PRIMARY KEY (id), -- 主键

    INDEX idx_time (battle_time), -- 索引

    INDEX idx_cid (clan_id) -- 索引
);