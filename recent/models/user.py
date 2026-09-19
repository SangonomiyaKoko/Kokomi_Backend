from dataclasses import dataclass

from .mode import BattleMode


@dataclass(frozen=True, slots=True)
class UserStats:
    """用户战绩统计数据"""
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

    def is_cache_outdated(self, updated_at: int | None) -> bool:
        """检查 MySQL 数据是否比缓存更新"""
        if self.updated_at is None:
            return False
        if updated_at is None:
            return True
        return self.updated_at >= updated_at

    def battles_for(self, mode: BattleMode) -> int:
        """返回指定模式的战斗场次"""
        if mode == BattleMode.PVP:
            return self.pvp_battles
        elif mode == BattleMode.RANK:
            return self.ranked_battles
        elif mode == BattleMode.CLAN:
            return self.rating_battles
        else:
            raise ValueError(f'Unknown parameter {mode}')


@dataclass(frozen=True, slots=True)
class UserRecord:
    """用户配置数据"""
    user_level: int
    storage_limit: int
    last_query_at: int | None
    next_refresh_at: int | None

    @property
    def is_configured(self) -> bool:
        """用户配置是否有效"""
        return self.user_level > 0 and self.storage_limit > 0
