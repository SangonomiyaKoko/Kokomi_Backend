class CommonConfig:
    REFRESH_TASK_NAME = 'user_refresh'
    REFRESH_QUEUE_NAME = 'refresh_queue'
    STATUS_FIELDS = [
        'overdue', 
        'within_24h', 
        'within_week', 
        'within_month', 
        'within_quarter'
    ]
    USER_INIT_TABLE_LIST = [
        "T_user_clan",
        "T_user_stats",
        "T_user_cache",
        "T_user_random",
        "T_user_ranked",
        "T_user_config"
    ]
    CLAN_INIT_TABLE_LIST = [
        "T_clan_users",
        "T_clan_stats",
        "T_clan_team"
    ]
    SHIP_INIT_TABLE_LIST = [
        "T_ship_pvp_stats",
        "T_ship_stats_by_battles",
        "T_ship_stats_by_users",
        "T_ship_rating_distribution"
    ]


class ClanPolicy:
    # 计算工会活跃等级所用用户数量区间配置
    # 基于工会内用户数量，确定工会活跃度等级
    ACTIVITY_THRESHOLDS = [
        [10, 3],
        [30, 2],
        [50, 1]
    ]

    # 计算工会下次更新时间配置
    # 基于工会活跃等级，确定工会更新时间间隔
    NORMAL_STRATEGY = {
        "0-1": 21600,    # 6 HOURS
        "0-2": 43200,    # 12 HOURS
        "0-3": 93600     # 26 HOURS
    }

    # 公会战排行榜需要遍历的「联赛-分段」组合
    LEAGUE_LIST = [
        "0-1",
        "1-1", "1-2", "1-3",
        "2-1", "2-2", "2-3",
        "3-1", "3-2", "3-3",
        "4-1", "4-2", "4-3"
    ]

class UserPolicy:
    # 账号等级降级条件配置
    MAX_INACTIVE_DAYS = 60
    MAX_NO_BATTLE_DAYS = 180
    MAX_HIDDEN_PROFILE_DAYS = 30

    # 计算账号活跃等级所用时间区间配置
    # 基于账号上次活跃时间，确定账号活跃度等级
    ACTIVITY_THRESHOLDS = [
        # 按顺序遍历列表，小于 list[0] 则返回 list[1]，默认返回 9
        # 即 < 1 DAYS 返回 1, > 730 DAYS 返回 9
        [86400, 1],      # 1 DAYS
        [259200, 2],     # 3 DAYS
        [604800, 3],     # 7 DAYS
        [2592000, 4],    # 30 DAYS
        [7776000, 5],    # 90 DAYS
        [15552000, 6],   # 180 DAYS
        [31536000, 7],   # 365 DAYS
        [63072000, 8]    # 730 DAYS
    ]

    # 计算账号下次更新时间配置
    # 基于账号等级和活跃等级，确定账号更新时间间隔
    NORMAL_STRATEGY = {
        # Lv.0 用户更新策略（默认策略）
        "0-1": 93600,    # 26 HOURS (1.08 DAYS)
        "0-2": 172800,   # 2 DAYS
        "0-3": 259200,   # 3 DAYS
        "0-4": 432000,   # 5 DAYS
        "0-5": 604800,   # 7 DAYS
        "0-6": 1296000,  # 15 DAYS
        "0-7": 1728000,  # 20 DAYS
        "0-8": 2592000,  # 30 DAYS
        "0-9": 7776000,  # 90 DAYS
        
        # Lv.1 用户更新策略
        # 仅面向活跃度 7 及以下用户，即过去 365 天内活跃
        "1-1": 3600,     # 1 HOUR
        "1-2": 7200,     # 2 HOURS
        "1-3": 10800,    # 3 HOURS
        "1-4": 14400,    # 4 HOURS
        "1-5": 21600,    # 6 HOURS
        "1-6": 28800,    # 8 HOURS
        "1-7": 43200,    # 12 HOURS
        "1-8": 2592000,  # 30 DAYS
        "1-9": 5184000,  # 60 DAYS
        
        # Lv.2 用户更新策略
        # 仅面向活跃度 5 及以下用户，即过去 90 天内活跃
        "2-1": 600,      # 10 MINS
        "2-2": 1200,     # 20 MINS
        "2-3": 1500,     # 25 MINS
        "2-4": 1800,     # 30 MINS
        "2-5": 3600,     # 1 HOUR
        "2-6": 1296000,  # 15 DAYS
        "2-7": 1728000,  # 20 DAYS
        "2-8": 2592000,  # 30 DAYS
        "2-9": 5184000   # 60 DAYS
    }

    # 计算账号下次更新时间配置
    # 对于高等级高活跃度账号的特殊更新配置
    SPECIAL_STRATEGY = [
        [3600, 60],     # 1 MINS
        [10800, 180],   # 2 MINS
        [43200, 300],   # 5 MINS
        [68400, 420]    # 7 MINS
    ]

    # 账号保底更新策略
    FALLBACK_TIMEOUT = {
        "1": 86400,
        "2": 3600
    }