from __future__ import annotations

from settings import REGION
from models import (
    UserStats,
    ShipBattleStats,
    ModeBattleStats,
    BattleMode,
    ShipData,
    ShipDataCollection,
    UpdateContext
)

from .endpoints import EndpointRegistry
from .requester import FetchResult


class ResponseParser:
    """将API响应解析为领域模型"""

    @staticmethod
    def parse_response(ctx: UpdateContext, fr: FetchResult, updated_at: int) -> None:
        """解析账号响应为 UserStats（调用方需先通过 ResponseValidator）"""
        basic_data = fr.account.get(str(ctx.account_id))
        if basic_data is None:
            ctx.user_stats = UserStats(is_enabled=False, updated_at=updated_at)
            return

        if 'hidden_profile' in basic_data:
            ctx.user_stats = UserStats(is_public=False, updated_at=updated_at)
            return

        if 'statistics' not in basic_data:
            ctx.user_stats = UserStats(is_enabled=False, updated_at=updated_at)
            return

        statistics = basic_data.get('statistics', {})
        if 'basic' not in statistics:
            ctx.user_stats = UserStats(is_public=True, updated_at=updated_at)
            return

        basic = statistics.get('basic', {})
        karma = basic.get('karma', 0)
        leveling_points = basic.get('leveling_points', 0)
        if leveling_points >= 1_000_000:
            leveling_points -= 1_000_000
        last_battle_time = basic.get('last_battle_time', 0)
        if last_battle_time == 0:
            last_battle_time = None

        pve_statistics = statistics.get('pve', {})
        pvp_statistics = statistics.get('pvp', {})
        rank_statistics = statistics.get('rank_solo', {})
        if REGION == 'ru':
            solo_data = statistics.get('rating_solo', {})
            div_data = statistics.get('rating_div', {})
            clan_statistics = {
                'battles_count': solo_data.get('battles_count', 0) + div_data.get('battles_count', 0),
                'wins': solo_data.get('wins', 0) + div_data.get('wins', 0),
                'damage_dealt': solo_data.get('damage_dealt', 0) + div_data.get('damage_dealt', 0),
                'frags': solo_data.get('frags', 0) + div_data.get('frags', 0),
                'original_exp': solo_data.get('original_exp', 0) + div_data.get('original_exp', 0)
            }
        else:
            clan_statistics = {}

        ctx.user_stats = UserStats(
            is_public=True,
            total_battles=leveling_points,
            pve_battles=pve_statistics.get('battles_count', 0),
            pvp_battles=pvp_statistics.get('battles_count', 0),
            ranked_battles=rank_statistics.get('battles_count', 0),
            rating_battles=clan_statistics.get('battles_count', 0),
            karma=karma,
            last_battle_at=last_battle_time,
            updated_at=updated_at
        )
        ctx.mode_data = {
            BattleMode.PVP: ModeBattleStats.from_api_data(pvp_statistics),
            BattleMode.RANK: ModeBattleStats.from_api_data(rank_statistics),
            BattleMode.CLAN: ModeBattleStats.from_api_data(clan_statistics)
        }

        ship_collection = {}
        for mode, types in fr.ships.items():
            if mode not in ship_collection:
                ship_collection[mode] = ShipDataCollection()

            mode_collection: ShipDataCollection = ship_collection[mode]

            for data_type, response in types.items():
                mode_key = EndpointRegistry.mode_key(mode, data_type)
                stats_map = response.get(str(ctx.account_id), {}).get('statistics', {})
                for ship_id_str, ship_stats in stats_map.items():
                    battle_stats = ship_stats.get(mode_key, {})
                    if not battle_stats or battle_stats.get('battles_count', 0) == 0:
                        continue

                    ship_id = int(ship_id_str)
                    if not mode_collection.is_exists(ship_id):
                        mode_collection.add_ship_data(ship_id, ShipData())
                    mode_collection.add_type_data(
                        ship_id, data_type, ShipBattleStats.from_api_data(battle_stats)
                    )
                
        ctx.ship_data = ship_collection
