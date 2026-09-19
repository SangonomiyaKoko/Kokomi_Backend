class ServicesName:
    """各服务的名称常量，同时用于日志名、状态键与服务配置的索引"""

    ACCOUNT = 'Account'
    CACHE = 'UserCache'
    RECENT = 'Recent'
    MEMBER = 'ClanMember'
    SEASON = 'ClanSeason'
    STATS = 'ServerStats'

    @classmethod
    def to_list(cls) -> list[str]:
        """返回全部服务名称"""
        return [
            cls.ACCOUNT,
            cls.CACHE,
            cls.RECENT,
            cls.MEMBER,
            cls.SEASON,
            cls.STATS
        ]
