from __future__ import annotations

from typing import Optional

from db import sqlite_read_only
from loggers import logger
from models import (
    BattleMode,
    DataType,
    UpdateContext,
    ModePlan,
    SnapshotUpdatePlan,
    ShipLatestIndexParams,
    ShipIndexDataParams,
    ShipIndexMapParams,
    RecentStatsParams,
    ShipData,
    BASE_UPDATE_MODES,
    FULL_UPDATE_MODES,
)
from repository import ShipIndexDataRepository
from utils import StringUtils


class UpdatePlanner:
    """船只快照对比管理器：按模式生成整体更新计划"""

    @classmethod
    def build_plan(cls, ctx: UpdateContext) -> SnapshotUpdatePlan:
        """对比新旧船只数据，生成整体更新计划"""
        plan = SnapshotUpdatePlan()
        for mode in ctx.fetch_modes:
            plan.modes[mode] = cls._plan_mode(ctx, mode)
        plan.cache_params = cls._merge_cache(ctx, plan.modes)
        return plan

    @classmethod
    def _plan_mode(cls, ctx: UpdateContext, mode: BattleMode) -> ModePlan:
        """生成单个模式的更新计划（ship_map / data 行 / recent）"""
        cache = ctx.ship_cache  # 本地缓存数据
        mode_stats = ctx.mode_data.get(mode)  # 各模式下总体统计数据(API请求获取)
        collection = ctx.ship_data.get(mode)  # 各模式下船只数据合集(API请求获取)

        changed = False     # 标记是否发生变更
        ship_map = {}       # 待重新构建的ship_map数据
        cache_changes = {}  # 发生更改的latest_cache船只合集
        data_insert, data_update = [], []
        recent_ships = []

        mode_ships = collection.ship_ids
        for ship_id in mode_ships:
            ship_data = collection.get_ship_data(ship_id)
            new_battles = ship_data.battles
            if new_battles == 0:
                continue

            # 缓存中无此船：新船，快照归入昨日作为基线
            entry = cache.get_entry(ship_id)
            if entry is None:
                changed = True
                ship_map[ship_id] = ctx.yesterday_date
                cache_changes[ship_id] = (new_battles, ctx.yesterday_date)
                data_insert.append(ShipIndexDataParams.from_ship_data(ship_id, mode, ctx.yesterday_date, ship_data))
                if ctx.is_pro:
                    recent_ships.append((ship_id, ship_data, None, ctx.user_stats.last_battle_at))
                continue

            # 未变动：沿用旧索引
            old_battles = entry.get_battle(mode)
            if old_battles == new_battles:
                ship_map[ship_id] = entry.get_index(mode)
                continue

            # 数据发生变动
            changed = True
            ship_map[ship_id] = ctx.now_date
            cache_changes[ship_id] = (new_battles, ctx.now_date)
            if entry.get_index(mode) == ctx.now_date:
                # 同一天内再次更新：原地更新已有数据行
                data_update.append(ShipIndexDataParams.from_ship_data(ship_id, mode, ctx.now_date, ship_data))
            else:
                data_insert.append(ShipIndexDataParams.from_ship_data(ship_id, mode, ctx.now_date, ship_data))
            if ctx.is_pro:
                recent_ships.append((ship_id, ship_data, entry, ctx.user_stats.last_battle_at))

        # 该模式下缓存有战绩但现已消失的船
        for ship_id in cache.ship_ids:
            entry = cache.get_entry(ship_id)
            old_battles = entry.get_battle(mode)
            if old_battles > 0 and ship_id not in mode_ships:
                changed = True
                cache_changes[ship_id] = (0, None)

        # 该模式无任何变动
        if not changed:
            return ModePlan(mode=mode, is_changed=False)

        # 构建 ship_index_map 行
        map_row = ShipIndexMapParams(
            ship_mode=mode.value,
            ship_index=ctx.now_date,
            ships=collection.count,
            battles=mode_stats.battles,
            wins=mode_stats.wins,
            damage=mode_stats.damage,
            frags=mode_stats.frags,
            exp=mode_stats.exp,
            index_map=StringUtils.index_map_encode(ship_map)
        )
        if cache.get_index(mode) == ctx.now_date:
            map_params = {'update': map_row}
        else:
            map_params = {'insert': map_row}

        # 近期差值计算（仅 Plus 用户）
        recent = []
        if ctx.is_pro and recent_ships:
            with sqlite_read_only(ctx.account_id) as cursor:
                for ship_id, ship_data, entry, lbt in recent_ships:
                    if not lbt or ctx.current_timestamp - lbt > 3600:
                        continue
                    old_data = None
                    old_index = entry.get_index(mode) if entry else None
                    if old_index is not None:
                        old_data = ShipIndexDataRepository.read(cursor, ship_id, mode, old_index)
                        if old_data is None:
                            logger.error(f'{ctx.account_id} | Missing snapshot `{ship_id}-{mode.name}-{old_index}`')
                            continue
                    recent.extend(cls.calc_recent_diff(mode, ship_id, ship_data, old_data, lbt))

        return ModePlan(
            mode=mode,
            is_changed=True,
            no_stats=True if mode_stats.battles == 0 else False,
            map_index=ctx.now_date,
            map_params=map_params,
            data_params={'insert': data_insert, 'update': data_update},
            cache_changes=cache_changes,
            recent=recent
        )

    @classmethod
    def _merge_cache(cls, ctx: UpdateContext, mode_plans: dict) -> dict:
        """合并各模式的船只缓存变动为全行状态的 insert/update/delete"""
        cache = ctx.ship_cache
        changed_ids = set()
        for mode_plan in mode_plans.values():
            changed_ids |= set(mode_plan.cache_changes.keys())

        insert, update = [], []
        for ship_id in changed_ids:
            entry = cache.get_entry(ship_id)
            pvp_change = mode_plans[BattleMode.PVP].cache_changes.get(ship_id) if BattleMode.PVP in mode_plans else None
            rank_change = mode_plans[BattleMode.RANK].cache_changes.get(ship_id) if BattleMode.RANK in mode_plans else None
            clan_change = mode_plans[BattleMode.CLAN].cache_changes.get(ship_id) if BattleMode.CLAN in mode_plans else None

            if entry is None:
                insert.append(ShipLatestIndexParams(
                    ship_id=ship_id,
                    pvp_battles=pvp_change[0] if pvp_change else 0,
                    rank_battles=rank_change[0] if rank_change else 0,
                    clan_battles=clan_change[0] if clan_change else 0,
                    pvp_index=pvp_change[1] if pvp_change else None,
                    rank_index=rank_change[1] if rank_change else None,
                    clan_index=clan_change[1] if clan_change else None,
                ))
            else:
                update.append(ShipLatestIndexParams(
                    ship_id=ship_id,
                    pvp_battles=pvp_change[0] if pvp_change else entry.get_battle(BattleMode.PVP),
                    rank_battles=rank_change[0] if rank_change else entry.get_battle(BattleMode.RANK),
                    clan_battles=clan_change[0] if clan_change else entry.get_battle(BattleMode.CLAN),
                    pvp_index=pvp_change[1] if pvp_change else entry.get_index(BattleMode.PVP),
                    rank_index=rank_change[1] if rank_change else entry.get_index(BattleMode.RANK),
                    clan_index=clan_change[1] if clan_change else entry.get_index(BattleMode.CLAN),
                ))

        return {'insert': insert, 'update': update}

    @staticmethod
    def calc_recent_diff(
        mode: BattleMode,
        ship_id: int,
        new_data: ShipData,
        old_data: Optional[ShipData],
        battle_time: int,
    ) -> list:
        """计算新旧船只数据的差值（按 mode 内的 data_type 生成多条记录）"""
        params = []
        for data_type in (DataType.SOLO, DataType.DIV2, DataType.DIV3):
            new_sbs = new_data.get_type_stats(data_type)
            if new_sbs is None:
                continue
            new_list = new_sbs.to_list()
            old_sbs = old_data.get_type_stats(data_type) if old_data else None
            old_list = old_sbs.to_list() if old_sbs else [0] * 12

            delta_battles = new_list[0] - old_list[0]
            if delta_battles <= 0:
                continue

            delta_hits = new_list[10] - old_list[10]
            delta_shots = new_list[11] - old_list[11]
            hit_rate = (
                round(delta_hits / delta_shots * 100, 2)
                if delta_shots != 0
                else 0.0
            )

            params.append(RecentStatsParams(
                ship_id=ship_id,
                data_mode=mode.value,
                data_type=data_type.value,
                battles=delta_battles,
                wins=new_list[1] - old_list[1],
                losses=new_list[2] - old_list[2],
                damage=new_list[3] - old_list[3],
                frags=new_list[4] - old_list[4],
                survived=new_list[5] - old_list[5],
                scout_damage=new_list[6] - old_list[6],
                art_agro=new_list[7] - old_list[7],
                exp=new_list[8] - old_list[8],
                planes=new_list[9] - old_list[9],
                hit_rate=hit_rate,
                battle_time=battle_time,
            ))
        return params
