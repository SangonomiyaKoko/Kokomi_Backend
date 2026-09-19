from .constants import ClanPolicy, UserPolicy

DAY_IN_SECONDS = 86400

class PolicyUtils:

    @staticmethod
    def clan_refresh_interval(activity_level: int) -> int:
        """基于公会活跃等级返回公会下次更新间隔（秒）"""
        return ClanPolicy.NORMAL_STRATEGY.get(
            f'0-{activity_level}',
            30 * DAY_IN_SECONDS
        )

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
    def clan_activity_level(members: int) -> int:
        """基于公会成员数量返回公会活跃等级"""
        for threshold, level in ClanPolicy.ACTIVITY_THRESHOLDS:
            if members <= threshold:
                return level

        return 0

    @staticmethod
    def user_hidden_policy(
        user_level: int
    ) -> int:
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
        level_key = str(user_level)
        return UserPolicy.FALLBACK_TIMEOUT.get(level_key, DAY_IN_SECONDS)