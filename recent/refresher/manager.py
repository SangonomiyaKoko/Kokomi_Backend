from db import sqlite_read_only
from loggers import logger
from repository import ShipSnapshotRepository
from models import (
    UpdateContext,
    SnapshotUpdatePlan,
    ShipCacheParams,
    ShipSnapshotParams,
    DailyIndexParams,
    RecentStatsParams,
    SingleShipData
)


class SnapshotManager:
    """船只快照对比管理器"""

    @classmethod
    def compare(cls, ctx: UpdateContext) -> SnapshotUpdatePlan:
        """对比新旧船只数据，生成快照更新计划"""
        plan = SnapshotUpdatePlan()
        local_cache = ctx.ship_cache  # 本地缓存
        battle_stats = ctx.ship_data  # API 数据

        ship_map = {}
        changed_ships = set()
        ship_count = battle_stats.count

        # 在本地没有用户的缓存数据
        if local_cache.date is None:
            for ship_id, ship_data in battle_stats:
                ship_map[ship_id] = ctx.yesterday_date
                plan.cache['insert'].append(ShipCacheParams(ship_id, ship_data.battles, ctx.yesterday_date))
                plan.snapshot['insert'].append(ShipSnapshotParams(ship_id, ctx.yesterday_date, ship_data))
            plan.count = ship_count
            plan.table = ctx.yesterday_date
            plan.index['insert'] = DailyIndexParams(ctx.yesterday_date, ship_count, ship_map)
            return plan

        for ship_id, ship_data in battle_stats:
            battle_count, ship_index = local_cache.get_ship_tuple(ship_id)

            # 本地缓存中没有船只：新建记录
            if battle_count is None:
                changed_ships.add(ship_id)
                ship_map[ship_id] = ctx.yesterday_date
                plan.cache['insert'].append(ShipCacheParams(ship_id, ship_data.battles, ctx.yesterday_date))
                plan.snapshot['insert'].append(ShipSnapshotParams(ship_id, ctx.yesterday_date, ship_data))
                continue

            # 数据未变动，沿用旧索引
            if ship_data.battles == battle_count:
                ship_map[ship_id] = ship_index
                continue

            # 本地缓存中已有船只：数据发生变动
            changed_ships.add(ship_id)
            ship_map[ship_id] = ctx.now_date
            plan.cache['update'].append(ShipCacheParams(ship_id, ship_data.battles, ctx.now_date))
            if ship_index == ctx.now_date:
                # 同一天内更新：update 已有快照
                plan.snapshot['update'].append(ShipSnapshotParams(ship_id, ctx.now_date, ship_data))
            else:
                # 跨天更新：insert 新快照
                plan.snapshot['insert'].append(ShipSnapshotParams(ship_id, ctx.now_date, ship_data))

        # 处理已在本地缓存但不再出现在最新数据中的船只（已出售/删除）
        for ship_id in local_cache.get_ship_ids():
            if not battle_stats.is_exists(ship_id):
                plan.cache['delete'].append(ShipCacheParams(ship_id))
                changed_ships.add(ship_id)

        if len(changed_ships) == 0:
            plan.is_changed = False
            plan.table = ctx.latest_summary.index_table
            return plan
        
        plan.count = ship_count
        plan.table = ctx.now_date
        if local_cache.date == ctx.now_date:
            plan.index['update'] = DailyIndexParams(ctx.now_date, ship_count, ship_map)
        else:
            plan.index['insert'] = DailyIndexParams(ctx.now_date, ship_count, ship_map)
        recent_ship = []
        
        if ctx.is_pro:
            with sqlite_read_only(ctx.account_id) as cursor:
                for ship_id in changed_ships:
                    ship_data = battle_stats.get_ship_data(ship_id)
                    if ship_data is None or ship_data.battles == 0:
                        continue

                    battle_count, ship_index = local_cache.get_ship_tuple(ship_id)

                    if battle_count is None or ship_index is None:
                        recent_ship.append((ship_id, ship_data, None))
                        continue

                    if battle_count >= ship_data.battles:
                        continue

                    ship_snapshot = ShipSnapshotRepository.read(cursor, ship_id, ship_index)
                    if not ship_snapshot:
                        logger.error(f'{ctx.account_id} | Missing snapshot `{ship_id}-{ship_index}`')
                        continue

                    recent_ship.append((ship_id, ship_data, ship_snapshot))

        for ship_id, new_stats, old_stats in recent_ship:
            plan.recent.extend(cls.calc_recent_diff(ship_id, new_stats, old_stats))
            
        return plan

    @staticmethod
    def calc_recent_diff(
        ship_id: int,
        new_stats: SingleShipData,
        old_stats: SingleShipData | None
    ) -> list[RecentStatsParams]:
        """计算新旧船只数据的差值"""
        modes = ['pvp_solo', 'pvp_div2', 'pvp_div3', 'rank_solo']
        params = []

        for idx, mode in enumerate(modes):
            new_sbs = new_stats.get_mode_stats(idx)
            if new_sbs is None:
                continue
            new_data = new_sbs.to_list()

            old_sbs = old_stats.get_mode_stats(idx)
            if old_sbs:
                old_data = old_sbs.to_list()
            else:
                old_data = [0] * 12

            # 计算各字段差值（新 - 旧）
            delta_battles = new_data[0] - old_data[0]
            if delta_battles <= 0:
                continue

            delta_wins = new_data[1] - old_data[1]
            delta_losses = new_data[2] - old_data[2]
            delta_damage = new_data[3] - old_data[3]
            delta_frags = new_data[4] - old_data[4]
            delta_original_exp = new_data[8] - old_data[8]
            delta_scouting_damage = new_data[6] - old_data[6]
            delta_art_agro = new_data[7] - old_data[7]
            delta_planes_killed = new_data[9] - old_data[9]
            delta_survived = new_data[5] - old_data[5]

            delta_hits = new_data[10] - old_data[10]
            delta_shots = new_data[11] - old_data[11]
            hit_rate = (
                round(delta_hits / delta_shots * 100, 2)
                if delta_shots != 0
                else 0.0
            )

            params.append(
                RecentStatsParams(
                    ship_id=ship_id,
                    mode=mode,
                    battles=delta_battles,
                    wins=delta_wins,
                    losses=delta_losses,
                    damage=delta_damage,
                    frags=delta_frags,
                    original_exp=delta_original_exp,
                    scouting_damage=delta_scouting_damage,
                    art_agro=delta_art_agro,
                    planes_killed=delta_planes_killed,
                    survived=delta_survived,
                    hit_rate=hit_rate,
                )
            )

        return params
