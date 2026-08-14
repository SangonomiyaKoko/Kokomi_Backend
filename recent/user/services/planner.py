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
        cache = ctx.ship_cache
        collection = ctx.ship_data.get(mode)
        mode_ships = list(collection.ships.items()) if collection else []

        ship_map = {}
        cache_changes = {}
        data_insert, data_update = [], []
        recent_ships = []
        changed = False

        for ship_id, ship_data in mode_ships:
            entry = cache.get_entry(ship_id)
            new_battles = ship_data.battles

            if entry is None:
                # 缓存中无此船：新船，快照归入昨日作为基线
                changed = True
                index = ctx.yesterday_date
                ship_map[ship_id] = index
                cache_changes[ship_id] = (new_battles, index)
                data_insert.append(ShipIndexDataParams.from_ship_data(
                    ship_id, mode, index, ship_data
                ))
                if ctx.is_pro:
                    recent_ships.append((ship_id, ship_data, None))
                continue

            old_battles = entry.get_battle(mode)
            if old_battles == new_battles:
                # 未变动：沿用旧索引
                ship_map[ship_id] = entry.get_index(mode)
                continue

            # 数据发生变动
            changed = True
            index = ctx.now_date
            ship_map[ship_id] = index
            cache_changes[ship_id] = (new_battles, index)
            if entry.get_index(mode) == index:
                # 同一天内再次更新：原地更新已有数据行
                data_update.append(ShipIndexDataParams.from_ship_data(
                    ship_id, mode, index, ship_data
                ))
            else:
                data_insert.append(ShipIndexDataParams.from_ship_data(
                    ship_id, mode, index, ship_data
                ))
            if ctx.is_pro:
                recent_ships.append((ship_id, ship_data, entry))

        # 该模式下缓存有战绩但现已消失的船（出售/该模式清空）：强制重建 map，将其从 ship_map 剔除
        mode_ship_ids = {ship_id for ship_id, _ in mode_ships}
        for ship_id in cache.get_ship_ids():
            entry = cache.get_entry(ship_id)
            if (entry.get_battle(mode) or 0) > 0 and ship_id not in mode_ship_ids:
                changed = True

        if not changed:
            # 该模式无任何变动：沿用上一个 summary 索引
            index = 0 if ctx.latest_summary is None else ctx.latest_summary.get_index(mode)
            return ModePlan(mode=mode, is_changed=False, map_index=index)

        # 构建 ship_index_map 行（聚合数据来自 mode_data 的简略统计）
        map_index = ctx.now_date
        ships_count = len(mode_ships)
        mode_stats = ctx.mode_data.get(mode)

        map_row = ShipIndexMapParams(
            ship_mode=mode.value,
            ship_index=map_index,
            ships=ships_count,
            battles=mode_stats.battles if mode_stats else 0,
            wins=mode_stats.wins if mode_stats else 0,
            damage=mode_stats.damage if mode_stats else 0,
            frags=mode_stats.frags if mode_stats else 0,
            exp=mode_stats.exp if mode_stats else 0,
            index_map=StringUtils.index_map_encode(ship_map),
        )
        if cache.get_index(mode) == ctx.now_date:
            map_params = {'update': map_row}
        else:
            map_params = {'insert': map_row}

        # 近期差值计算（仅 Plus 用户）
        recent = []
        if ctx.is_pro and recent_ships:
            with sqlite_read_only(ctx.account_id) as cursor:
                for ship_id, ship_data, entry in recent_ships:
                    old_data = None
                    old_index = entry.get_index(mode) if entry else None
                    if old_index is not None:
                        old_data = ShipIndexDataRepository.read(cursor, ship_id, mode, old_index)
                        if old_data is None:
                            logger.error(
                                f'{ctx.account_id} | Missing snapshot `{ship_id}-{mode.name}-{old_index}`'
                            )
                            continue
                    recent.extend(cls.calc_recent_diff(
                        mode, ship_id, ship_data, old_data, ctx.current_timestamp
                    ))

        return ModePlan(
            mode=mode,
            is_changed=True,
            map_index=map_index,
            map_params=map_params,
            data_params={'insert': data_insert, 'update': data_update},
            cache_changes=cache_changes,
            recent=recent,
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
                    pvp_battles=pvp_change[0] if pvp_change else (entry.get_battle(BattleMode.PVP) or 0),
                    rank_battles=rank_change[0] if rank_change else (entry.get_battle(BattleMode.RANK) or 0),
                    clan_battles=clan_change[0] if clan_change else (entry.get_battle(BattleMode.CLAN) or 0),
                    pvp_index=pvp_change[1] if pvp_change else entry.get_index(BattleMode.PVP),
                    rank_index=rank_change[1] if rank_change else entry.get_index(BattleMode.RANK),
                    clan_index=clan_change[1] if clan_change else entry.get_index(BattleMode.CLAN),
                ))

        # 已从所有模式消失的船（出售/清空）：仅当全量请求时才能确认删除，避免误删仍存在于未请求模式的船
        delete = []
        if ctx.fetch_modes == BASE_UPDATE_MODES or ctx.fetch_modes == FULL_UPDATE_MODES:
            for ship_id in cache.get_ship_ids():
                if cls._is_ship_gone(ctx, ship_id):
                    delete.append(ShipLatestIndexParams(ship_id=ship_id))

        return {'insert': insert, 'update': update, 'delete': delete}

    @staticmethod
    def _is_ship_gone(ctx: UpdateContext, ship_id: int) -> bool:
        """判断船只是否在本次请求的所有模式中均不再出现"""
        for mode in ctx.fetch_modes:
            collection = ctx.ship_data.get(mode)
            if collection is not None and collection.is_exists(ship_id):
                return False
        return True

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
