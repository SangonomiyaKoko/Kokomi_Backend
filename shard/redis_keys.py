class RedisKeys:
    """用于返回 Redis 键名"""

    @staticmethod
    def services(
        name: str
    ) -> str:
        return f"status:{name}"

    @staticmethod
    def metrics(
        name: str,
        index: str,
        date: str
    ) -> str:
        return f"metrics:{name}:{index}:{date}"

    @staticmethod
    def queue_lock(
        spaid: int
    ) -> str:
        """用于账号调度器与 Celery 刷新任务之间的入队锁"""
        return f"refresh_lock:queue:{spaid}"

    @staticmethod
    def insert_lock() -> str:
        """用于跨服务插入新用户时的互斥锁"""
        return "refresh_lock:insert"

    @staticmethod
    def recent_lock(
        spaid: int
    ) -> str:
        """用于 Recent 用户刷新分布式锁"""
        return f"refresh_lock:recent:{spaid}"

    @staticmethod
    def user_lock(
        spaid: int
    ) -> str:
        """用于用户刷新分布式锁"""
        return f"refresh_lock:user:{spaid}"

    @staticmethod
    def user_ac_token(
        spaid: int
    ) -> str:
        return f"token:ac:{spaid}"

    @staticmethod
    def clan_zrank() -> str:
        return "leaderboard:clan"