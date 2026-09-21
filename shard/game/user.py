DAY_IN_SECONDS = 86400


class UserPolicy:
    """账号等级、活跃等级与更新间隔的策略配置"""

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


class UserPolicyUtils:
    """基于 UserPolicy 推导账号活跃等级与更新间隔"""

    @staticmethod
    def max_hidden_days() -> int:
        """账号隐藏战绩触发账号等级降级的条件"""
        return UserPolicy.MAX_HIDDEN_PROFILE_DAYS

    @staticmethod
    def max_user_inactive_interval() -> int:
        """用户不活跃触发账号等级降级的条件"""
        return UserPolicy.MAX_INACTIVE_DAYS * DAY_IN_SECONDS

    @staticmethod
    def max_battle_inactive_interval() -> int:
        """账号不活跃触发账号等级降级的条件"""
        return UserPolicy.MAX_NO_BATTLE_DAYS * DAY_IN_SECONDS

    @staticmethod
    def user_activity_level(
        timestamp: int, lbt: int = None
    ) -> int:
        """基于用户最后战斗时间戳返回用户活跃等级"""
        if not lbt or lbt <= 0:
            return 0

        diff = timestamp - lbt
        for threshold, level in UserPolicy.ACTIVITY_THRESHOLDS:
            if diff <= threshold:
                return level

        # 超过配置最大时间区间统一返回 9
        return 9

    @staticmethod
    def user_hidden_policy(
        user_level: int
    ) -> int:
        """隐藏战绩账号的更新间隔"""
        if user_level > 0:
            return DAY_IN_SECONDS
        else:
            return 30 * DAY_IN_SECONDS

    @staticmethod
    def user_normal_policy(
        timestamp: int,
        user_level: int,
        activity_level: int,
        lbt: int
    ) -> int:
        """普通账号的更新间隔"""
        if user_level == 2 and activity_level == 1:
            interval_seconds = 600  # 默认 10min

            diff_timestamp = timestamp - lbt
            for item in UserPolicy.SPECIAL_STRATEGY:
                if diff_timestamp < item[0]:
                    interval_seconds = item[1]
                    break

            return interval_seconds
        else:
            user_key = f"{user_level}-{activity_level}"
            return UserPolicy.NORMAL_STRATEGY.get(user_key, DAY_IN_SECONDS)

    @staticmethod
    def recent_fallback_timeout(
        user_level: int
    ) -> int:
        """账号保底更新间隔"""
        level_key = str(user_level)
        return UserPolicy.FALLBACK_TIMEOUT.get(level_key, DAY_IN_SECONDS)
