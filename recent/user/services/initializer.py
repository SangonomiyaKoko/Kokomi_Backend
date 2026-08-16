from __future__ import annotations

from db import sqlite_transaction
from models import (
    UpdateContext,
    BattleMode,
    ShipLatestIndexParams,
    ShipIndexDataParams,
    ShipIndexMapParams,
    FULL_UPDATE_MODES
)
from repository import (
    DailySummaryRepository,
    ShipCacheRepository,
    ShipIndexDataRepository,
    ShipIndexMapRepository,
)
from utils import StringUtils


class UserInitializer:
    """新用户初始化器：全量写入初始快照"""

    @classmethod
    def main(cls, ctx: UpdateContext) -> str:
        """主入口：初始化新用户数据库"""
        try:
            indices = cls._build_indices(ctx)
            with sqlite_transaction(ctx.account_id) as cursor:
                cls._write_index_data(cursor, ctx)
                cls._write_index_map(cursor, ctx)
                cls._write_latest_index(cursor, ctx, indices)
                cls._write_summary(cursor, ctx, indices)
        except Exception:
            return 'Exception'
        return 'Initialized'

    @staticmethod
    def _build_indices(ctx: UpdateContext) -> dict[BattleMode, int]:
        """各模式索引：有数据 → yesterday_date，无数据 → 0（NULL=未记录 0=无数据 日期=有数据）"""
        indices = {}
        for mode in ctx.fetch_modes:
            mode_stats = ctx.mode_data.get(mode)
            if mode_stats is None:
                indices[mode] = None
            if mode_stats.battles > 0:
                indices[mode] = ctx.yesterday_date
            else:
                indices[mode] = 0
        return indices

    @staticmethod
    def _write_index_data(cursor, ctx: UpdateContext) -> None:
        """为每艘船在每个模式下写入一条 ship_index_data"""
        data_insert = []
        for mode in ctx.fetch_modes:
            # 检测该模式下是否存在统计数据
            mode_stats = ctx.mode_data.get(mode)
            if mode_stats.battles == 0:
                continue

            collection = ctx.ship_data.get(mode)
            for ship_id, ship_data in collection:
                data_insert.append(ShipIndexDataParams.from_ship_data(ship_id, mode, ctx.yesterday_date, ship_data))
        if data_insert:
            ShipIndexDataRepository.refresh(cursor, {'insert': data_insert})

    @staticmethod
    def _write_index_map(cursor, ctx: UpdateContext) -> None:
        """为每个有数据的模式写入一条 ship_index_map 记录"""
        for mode in ctx.fetch_modes:
            mode_stats = ctx.mode_data.get(mode)
            if mode_stats.battles == 0:
                continue
            
            collection = ctx.ship_data.get(mode)
            ship_map = {
                ship_id: ctx.yesterday_date for ship_id in collection.ships
            }
            map_row = ShipIndexMapParams(
                ship_mode=mode.value,
                ship_index=ctx.yesterday_date,
                ships=collection.count,
                battles=mode_stats.battles,
                wins=mode_stats.wins,
                damage=mode_stats.damage,
                frags=mode_stats.frags,
                exp=mode_stats.exp,
                index_map=StringUtils.index_map_encode(ship_map),
            )
            ShipIndexMapRepository.refresh(cursor, {'insert': map_row})

    @staticmethod
    def _write_latest_index(cursor, ctx: UpdateContext, indices: dict) -> None:
        """写入普通船只缓存行（全 INSERT）+ 特殊行（UPDATE）"""
        # 特殊行：记录各模式最新战斗数与 map 索引
        ShipCacheRepository.record_latest_index(
            cursor,
            pvp=(ctx.user_stats.pvp_battles, indices.get(BattleMode.PVP)),
            rank=(ctx.user_stats.ranked_battles, indices.get(BattleMode.RANK)),
            clan=(ctx.user_stats.rating_battles, indices.get(BattleMode.CLAN))
        )

        # 合并各模式，收集每艘船在各模式的 (battles, index)
        entries: dict[int, dict[BattleMode, tuple]] = {}
        for mode in ctx.fetch_modes:
            # 检测该模式下是否存在统计数据
            mode_stats = ctx.mode_data.get(mode)
            if mode_stats.battles == 0:
                continue

            collection = ctx.ship_data.get(mode)
            for ship_id, ship_data in collection:
                entries.setdefault(ship_id, {})[mode] = (ship_data.battles, ctx.yesterday_date)
                
        default_tuple = (0, None)
        insert_params = [
            ShipLatestIndexParams(
                ship_id=ship_id,
                pvp_battles=mode_map.get(BattleMode.PVP, default_tuple)[0],
                rank_battles=mode_map.get(BattleMode.RANK, default_tuple)[0],
                clan_battles=mode_map.get(BattleMode.CLAN, default_tuple)[0],
                pvp_index=mode_map.get(BattleMode.PVP, default_tuple)[1],
                rank_index=mode_map.get(BattleMode.RANK, default_tuple)[1],
                clan_index=mode_map.get(BattleMode.CLAN, default_tuple)[1],
            )
            for ship_id, mode_map in entries.items()
        ]
        if insert_params:
            ShipCacheRepository.refresh(cursor, {'insert': insert_params})

    @staticmethod
    def _write_summary(cursor, ctx: UpdateContext, indices: dict) -> None:
        """写入昨日与今日两条 summary（内容一致，均指向初始基线快照）"""
        summary = DailySummaryRepository.from_stats(ctx.user_stats, indices)
        DailySummaryRepository.insert(cursor, ctx.yesterday_date, summary)
        DailySummaryRepository.insert(cursor, ctx.now_date, summary)
