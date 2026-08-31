from settings import REGION
from context import UpdateContext
from models import (
    UserStats,
    BattleMode,
    ShipBattleStats,
    ModeBattleStats,
    ShipDataCollection,
    LatestDataEntry
)

from .endpoints import EndpointRegistry
from .requester import FetchResult


class ResponseParser:
    """将 API 响应解析为领域模型"""

    @staticmethod
    def parse_response(ctx: UpdateContext, fr: FetchResult, updated_at: int) -> None:
        """解析返回的用户总体数据和各模式的详细数据，并写入 ctx.user_stats 和 ctx.latest_data"""
        # 解析用户总体数据流程
        basic_data = fr.account.get(str(ctx.account_id))
        if basic_data is None:
            # 用户不存在
            ctx.user_stats = UserStats(is_enabled=False, updated_at=updated_at)
            return

        if 'hidden_profile' in basic_data:
            # 用户隐藏战绩
            ctx.user_stats = UserStats(is_public=False, updated_at=updated_at)
            return

        if 'statistics' not in basic_data:
            # 用户不存在，需要先排除隐藏战绩导致的没有 statistics 字段
            ctx.user_stats = UserStats(is_enabled=False, updated_at=updated_at)
            return

        statistics = basic_data.get('statistics', {})
        if 'basic' not in statistics:
            # 用户存在但无统计数据，属于新用户
            ctx.user_stats = UserStats(is_public=True, updated_at=updated_at)
            mode_data = {
                BattleMode.PVP: ModeBattleStats.from_api({}),
                BattleMode.RANK: ModeBattleStats.from_api({}),
                BattleMode.CLAN: ModeBattleStats.from_api({})
            }
            ship_collection = {mode: ShipDataCollection() for mode in ctx.fetch_modes}
            for mode in ctx.fetch_modes:
                ctx.latest_data[mode] = LatestDataEntry(
                    mode = mode_data[mode],
                    ship = ship_collection[mode]
                )
            return

        basic = statistics.get('basic', {})
        karma = basic.get('karma', 0)
        leveling_points = basic.get('leveling_points', 0)
        if leveling_points >= 1_000_000:
            # 处理中国服存在的特殊账号
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
                'battles_count': (
                    solo_data.get('battles_count', 0)
                    + div_data.get('battles_count', 0)
                ),
                'wins': solo_data.get('wins', 0) + div_data.get('wins', 0),
                'damage_dealt': (
                    solo_data.get('damage_dealt', 0)
                    + div_data.get('damage_dealt', 0)
                ),
                'frags': solo_data.get('frags', 0) + div_data.get('frags', 0),
                'original_exp': (
                    solo_data.get('original_exp', 0)
                    + div_data.get('original_exp', 0)
                ),
            }
        else:
            clan_statistics = {
                'battles_count': 0,
                'wins': 0,
                'damage_dealt': 0,
                'frags': 0,
                'original_exp': 0
            }

        # 读取用户总体数据下各模式的总体概览数据
        # 特殊说明：
        # 用户总体数据接口下的模式的总战斗场次和该模式详细数据接口中所有船只累加的总战斗场次可能不一致
        # 数据库储存的顶层中记录的是用户总体数据接口下的模式的总战斗场次，是否更新也是基于此数值是否变动
        # 此为 WG 接口的内部问题，但是不会影响到当前更新的逻辑
        mode_data = {
            BattleMode.PVP: ModeBattleStats.from_api(pvp_statistics),
            BattleMode.RANK: ModeBattleStats.from_api(rank_statistics),
            BattleMode.CLAN: ModeBattleStats.from_api(clan_statistics)
        }

        # 解析各模式下船只合集数据
        ship_collection = {}
        for mode, types in fr.ships.items():
            ship_collection.setdefault(mode, ShipDataCollection())
            mode_collection: ShipDataCollection = ship_collection[mode]
            for data_type, response in types.items():
                if mode == BattleMode.CLAN and REGION in ['asia', 'eu', 'na']:
                    # 直营服 CLAN 模式接口的特殊处理
                    # 在用户基本数据接口中读取不到 CLAN 模式的概览数据，因此需要自行累加计算
                    stats_list = response.get(
                        str(ctx.account_id), []
                    ) or []
                    for ship_stats in stats_list:
                        battle_stats = ship_stats.get('clan', {})
                        if battle_stats.get('battles', 0) == 0:
                            continue

                        clan_statistics['battles_count'] += battle_stats.get('battles', 0)
                        clan_statistics['wins'] += battle_stats.get('wins', 0)
                        clan_statistics['damage_dealt'] += battle_stats.get('damage_dealt', 0)
                        clan_statistics['frags'] += battle_stats.get('frags', 0)
                        # 该接口返回的经验是经过加成的数据，但是 CLAN 模式的实际经验可以通过场次进行推算
                        # 胜利为 2500 EXP，而失败或者平局则为 250 EXP
                        total_exp = (
                            battle_stats.get('wins', 0) * 2500
                            + battle_stats.get('losses', 0) * 250
                            + battle_stats.get('draws', 0) * 250
                        )
                        clan_statistics['original_exp'] += total_exp

                        ship_id = ship_stats.get('ship_id')
                        mode_collection.setdefault(ship_id)
                        mode_collection.set_type_data(
                            ship_id, data_type, ShipBattleStats.from_api2(battle_stats)
                        )
                    # 替换原本的 Stats 数据
                    mode_data[BattleMode.CLAN] = ModeBattleStats.from_api(clan_statistics)
                else:
                    # 正常模式下的处理逻辑
                    mode_key = EndpointRegistry.mode_key(mode, data_type)
                    stats_map = response.get(
                        str(ctx.account_id), {}
                    ).get('statistics', {})
                    for ship_id_str, ship_stats in stats_map.items():
                        battle_stats = ship_stats.get(mode_key, {})
                        if battle_stats.get('battles_count', 0) == 0:
                            continue

                        ship_id = int(ship_id_str)
                        mode_collection.setdefault(ship_id)
                        mode_collection.set_type_data(
                            ship_id, data_type, ShipBattleStats.from_api(battle_stats),
                        )

        # 如果直营服本次读取的模式中不包含 CLAN 模式，则无法从接口中获取该模式的总战斗场次
        # 而后续更新 daily_summary 表需要基于完整的 user_stats 数据，因此需要读取本地数中的缓存数据来填补
        if (
            REGION in ['asia', 'eu', 'na'] and 
            BattleMode.CLAN not in ctx.fetch_modes and
            not ctx.access_token
        ):
            clan_statistics['battles_count'] = ctx.local_data[BattleMode.CLAN].battles

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

        for mode in ctx.fetch_modes:
            ctx.latest_data[mode] = LatestDataEntry(
                mode = mode_data[mode],
                ship = ship_collection[mode]
            )
