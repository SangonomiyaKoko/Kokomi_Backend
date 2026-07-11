class AppState:
    """全局应用状态管理

    用于在 app 启动时初始化并全局储存应用是否可用的状态。
    """

    _available: bool = True

    @classmethod
    def init(cls, available: bool) -> None:
        """初始化应用状态"""
        cls._available = available

    @classmethod
    def set_available(cls, available: bool) -> None:
        """设置应用可用状态"""
        cls._available = available

    @classmethod
    def is_available(cls) -> bool:
        """返回应用当前是否可用"""
        return cls._available
