from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class UserStats:
    """用户战绩统计数据（从数据库或API接口读取到的最新数据）"""
    is_enabled: bool = True
    is_public: bool = False
    total_battles: int = 0
    pve_battles: int = 0
    pvp_battles: int = 0
    ranked_battles: int = 0
    rating_battles: int = 0
    karma: int = 0
    last_battle_at: int = None
    updated_at: int = None

    @property
    def is_hidden(self) -> bool:
        """用户是否隐藏战绩"""
        return not self.is_public

    @property
    def is_valid(self) -> bool:
        """用户是否有效"""
        return self.is_enabled

    @property
    def no_competitive(self) -> bool:
        """用户是否有竞技类战绩（PVP/Rank）"""
        return self.pvp_battles + self.ranked_battles + self.rating_battles == 0

    def is_cache_outdated(self, updated_at: int | None) -> bool:
        """检查MySQL数据是否比缓存更新"""
        if self.updated_at is None:
            return False
        if updated_at is None:
            return True
        return self.updated_at >= updated_at

    def __str__(self) -> str:
        """输出字符串"""
        return (
            f"UserStats("
            f"is_enabled={self.is_enabled}, "
            f"is_public={self.is_public}, "
            f"total_battles={self.total_battles}, "
            f"pve_battles={self.pve_battles}, "
            f"pvp_battles={self.pvp_battles}, "
            f"ranked_battles={self.ranked_battles}, "
            f"karma={self.karma}, "
            f"last_battle_at={self.last_battle_at}, "
            f"updated_at={self.updated_at}"
            f")"
        )


@dataclass(frozen=True, slots=True)
class UserRecord:
    """用户在 MySQL 主库中的配置"""
    user_level: int
    storage_limit: int
    last_query_at: int | None
    next_refresh_at: int | None

    @property
    def is_configured(self) -> bool:
        """用户配置是否有效"""
        return self.user_level > 0 and self.storage_limit > 0

    def __str__(self) -> str:
        """输出字符串"""
        return (
            f"UserRecord("
            f"user_level={self.user_level}, "
            f"storage_limit={self.storage_limit}, "
            f"last_query_at={self.last_query_at}, "
            f"next_refresh_at={self.next_refresh_at}"
            f")"
        )
