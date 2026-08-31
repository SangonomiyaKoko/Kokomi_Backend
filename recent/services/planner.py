from dataclasses import replace

from loggers import logger
from db import sqlite_read_only
from context import UpdateContext
from utils import TimeUtils
from repository import ShipDataRepository
from models import (
    DataType,
    BattleMode,
    UpdateStrategy,
    FULL_UPDATE_MODES
)
from settings import REGION


class UpdatePlanner:
    """写回层：把拉取到的用户数据按模式落库"""

    @classmethod
    def main(cls, ctx: UpdateContext) -> str:
        """根据更新策略生成数据库写回计划"""
        if ctx.update_strategy == UpdateStrategy.NEW_USER:
            return cls._initialize(ctx)
        elif ctx.user_stats.is_hidden:
            return cls._mark_hidden(ctx)
        else:
            return cls._normal(ctx)

    @staticmethod
    def _initialize(ctx: UpdateContext) -> str:
        """生成新用户的完整初始化计划"""
        stats = ctx.user_stats

        for mode in ctx.fetch_modes:
            ship_map = {}
            mode_stats = ctx.latest_data[mode].mode
            collection = ctx.latest_data[mode].ship

            ctx.update_plan.mode_latest.set_update_params(
                ship_mode=mode,
                mode_data=mode_stats, 
                mode_index=ctx.yesterday_date, 
                updated_at=ctx.update_timestamp
            )
            for ship_id, ship_data in collection:
                if ship_data.battles == 0:
                    continue
                ship_map[ship_id] = ctx.yesterday_date
                ctx.update_plan.ship_data.set_insert_params(
                    ship_id=ship_id, 
                    ship_mode=mode, 
                    ship_index=ctx.yesterday_date, 
                    ship_data=ship_data
                )
                ctx.update_plan.ship_latest.set_insert_params(
                    ship_id=ship_id, 
                    ship_mode=mode, 
                    ship_data=ship_data.aggregate(), 
                    ship_index=ctx.yesterday_date
                )
            ctx.update_plan.ship_map.set_insert_params(
                ship_mode=mode, 
                ship_index=ctx.yesterday_date, 
                ship_map=ship_map, 
                ship_data=collection.aggregate(), 
                updated_at=ctx.update_timestamp
            )

        # 整理摘要写回的索引与统计
        indices = {
            BattleMode.PVP: ctx.yesterday_date,
            BattleMode.RANK: ctx.yesterday_date,
            BattleMode.CLAN: ctx.yesterday_date
        }
        if REGION == 'ru':
            new_stats = stats
        elif BattleMode.CLAN in ctx.fetch_modes:
            new_stats = replace(
                stats, 
                rating_battles=ctx.latest_data[BattleMode.CLAN].battles
            )
        else:
            new_stats = stats
            indices[BattleMode.CLAN] = None

        ctx.update_plan.user_summary.set_insert_params_from_stats(
            snapshot_date=ctx.yesterday_date, 
            stats=new_stats, 
            indices=indices
        )
        ctx.update_plan.user_summary.set_insert_params_from_stats(
            snapshot_date=ctx.now_date, 
            stats=new_stats, 
            indices=indices
        )

        return 'Initialize'

    @staticmethod
    def _mark_hidden(ctx: UpdateContext) -> str:
        """生成隐藏用户的摘要更新计划"""
        stats = ctx.user_stats

        # 按需将今日 summary 更新为隐藏状态
        if ctx.latest_summary.is_public:
            # 当前 summary 有战绩但更新时间非今日 → 更新为隐藏
            if TimeUtils.get_reset_date(stats.updated_at) != ctx.now_date:
                ctx.update_plan.user_summary.set_update_params_from_hidden(
                    snapshot_date=ctx.now_date, 
                    updated_at=ctx.update_timestamp
                )
        else:
            # 当前 summary 已是隐藏但更新时间过旧 → 刷新时间戳
            if stats.is_cache_outdated(ctx.latest_summary.updated_at):
                ctx.update_plan.user_summary.set_update_params_from_hidden(
                    snapshot_date=ctx.now_date, 
                    updated_at=ctx.update_timestamp
                )

        return 'Hidden'

    @classmethod
    def _normal(cls, ctx: UpdateContext) -> str:
        """生成普通用户的增量更新计划"""
        up = ctx.update_plan
        indices = {}
        recent_ships = []

        for mode in FULL_UPDATE_MODES:
            # 不在更新计划中则复用数据库中的数据索引
            if mode not in ctx.fetch_modes:
                indices[mode] = ctx.local_data[mode].mode_index
                continue

            # 本地数据库读取的数据
            local_mode_data = ctx.local_data[mode].mode
            local_ship_data = ctx.local_data[mode].ship

            # 数据接口获取的数据
            latest_mode_data = ctx.latest_data[mode].mode
            latest_ship_data = ctx.latest_data[mode].ship

            # 没有数据变动，直接跳过并复用数据库中的数据索引
            if local_mode_data.battles == latest_mode_data.battles:
                indices[mode] = local_mode_data.mode_index
                continue

            # 极低概率触发回档情况，写入日志文件
            if local_mode_data.battles > latest_mode_data.battles:
                logger.warning(
                    f'{ctx.account_id} | Detected data rollback: '
                    f'{mode.name} {local_mode_data.battles} -> {latest_mode_data.battles}'
                )

            # 有数据变动则更新数据索引
            indices[mode] = ctx.now_date

            # 接口返回该模式无战绩数据时的特殊处理
            if latest_mode_data.battles == 0:
                # 如果本地存在数据则置 0
                # 该情况仅账号回档后出现
                for ship_id, ship_data in local_ship_data:
                    if ship_data.battle == 0:
                        continue

                    if ship_data.index == ctx.now_date:
                        up.ship_data.set_update_params(
                            ship_id=ship_id, 
                            ship_mode=mode, 
                            ship_index=ctx.now_date, 
                            ship_data=None
                        )
                    else:
                        up.ship_data.set_insert_params(
                            ship_id=ship_id, 
                            ship_mode=mode, 
                            ship_index=ctx.now_date, 
                            ship_data=None
                        )
                    up.ship_latest.set_update_params(
                        ship_id=ship_id,
                        ship_mode=mode,
                        ship_data=None,
                        ship_index=ctx.now_date
                    )
                if local_mode_data.mode_index == ctx.now_date:
                    up.mode_latest.set_update_params(
                        ship_mode=mode, 
                        mode_data=latest_mode_data, 
                        mode_index=ctx.now_date, 
                        updated_at=ctx.update_timestamp
                    )
                    up.ship_map.set_update_params(
                        ship_mode=mode, 
                        ship_index=ctx.now_date, 
                        ship_map={}, 
                        ship_data=None, 
                        updated_at=ctx.update_timestamp
                    )
                else:
                    up.mode_latest.set_update_params(
                        ship_mode=mode, 
                        mode_data=latest_mode_data, 
                        mode_index=ctx.now_date, 
                        updated_at=ctx.update_timestamp
                    )
                    up.ship_map.set_insert_params(
                        ship_mode=mode, 
                        ship_index=ctx.now_date, 
                        ship_map={}, 
                        ship_data=None, 
                        updated_at=ctx.update_timestamp
                    )
                continue

            ship_map = {}
            compute_recent = ctx.is_pro and (mode != BattleMode.CLAN or REGION == 'ru')
            for ship_id, ship_data in latest_ship_data:
                if ship_data.battles == 0:
                    continue
                if not local_ship_data.is_exists(ship_id):
                    ship_map[ship_id] = ctx.yesterday_date
                    up.ship_data.set_insert_params(
                        ship_id=ship_id, 
                        ship_mode=mode, 
                        ship_index=ctx.yesterday_date, 
                        ship_data=ship_data
                    )
                    up.ship_latest.set_insert_params(
                        ship_id=ship_id,
                        ship_mode=mode,
                        ship_data=ship_data.aggregate(),
                        ship_index=ctx.yesterday_date
                    )
                    if compute_recent:
                        recent_ships.append((mode, ship_id, ship_data, None))
                    continue
                ship_entry = local_ship_data.get_entry(ship_id)
                if ship_entry.battle == ship_data.battles:
                    ship_map[ship_id] = ship_entry.index
                else:
                    ship_map[ship_id] = ctx.now_date
                    if ship_entry.index == ctx.now_date:
                        up.ship_data.set_update_params(
                            ship_id=ship_id, 
                            ship_mode=mode, 
                            ship_index=ctx.now_date, 
                            ship_data=ship_data
                        )
                    else:
                        up.ship_data.set_insert_params(
                            ship_id=ship_id, 
                            ship_mode=mode, 
                            ship_index=ctx.now_date, 
                            ship_data=ship_data
                        )
                    up.ship_latest.set_update_params(
                        ship_id=ship_id,
                        ship_mode=mode,
                        ship_data=ship_data.aggregate(),
                        ship_index=ctx.now_date
                    )
                    if compute_recent:
                        recent_ships.append((mode, ship_id, ship_data, ship_entry))


            up.mode_latest.set_update_params(
                ship_mode=mode, 
                mode_data=latest_mode_data, 
                mode_index=ctx.now_date, 
                updated_at=ctx.update_timestamp
            )
            if local_mode_data.mode_index == ctx.now_date:
                up.ship_map.set_update_params(
                    ship_mode=mode, 
                    ship_index=ctx.now_date, 
                    ship_map=ship_map, 
                    ship_data=latest_mode_data, 
                    updated_at=ctx.update_timestamp
                )
            else:
                up.ship_map.set_insert_params(
                    ship_mode=mode, 
                    ship_index=ctx.now_date, 
                    ship_map=ship_map, 
                    ship_data=latest_mode_data, 
                    updated_at=ctx.update_timestamp
                )

        # 按更新策略写回 daily_summary 记录
        if ctx.update_strategy == UpdateStrategy.MISSING_SUMMARY:
            up.user_summary.set_update_params_from_stats(
                snapshot_date=ctx.yesterday_date, 
                stats=ctx.user_stats, 
                indices=indices
            )
            up.user_summary.set_update_params_from_stats(
                snapshot_date=ctx.now_date, 
                stats=ctx.user_stats, 
                indices=indices
            )
        elif (
            BattleMode.CLAN in ctx.fetch_modes and 
            ctx.update_strategy == UpdateStrategy.SPECIAL_CLAN_UPDATE
        ):
            clan_mode_data = ctx.latest_data[BattleMode.CLAN].mode
            yestoday_summary = ctx.daily_summary[ctx.yesterday_date]
            replaced_summary = replace(
                yestoday_summary, 
                clan_battles=clan_mode_data.battles, 
                clan_index=indices[BattleMode.CLAN]
            )
            up.user_summary.set_update_params_from_local(
                snapshot_date=ctx.yesterday_date, 
                summary=replaced_summary
            )
            up.user_summary.set_update_params_from_stats(
                snapshot_date=ctx.now_date, 
                stats=ctx.user_stats, 
                indices=indices
            )
        else:
            up.user_summary.set_update_params_from_stats(
                snapshot_date=ctx.now_date, 
                stats=ctx.user_stats, 
                indices=indices
            )

        # 计算详细近期数据，仅 Plus 用户参与，CLAN 模式限俄服
        if recent_ships:
            cls._calc_recent(ctx, recent_ships)

        return 'Success'

    @staticmethod
    def _calc_recent(ctx: UpdateContext, recent_ships: list) -> None:
        """计算各船近期战斗差值，并写入 user_recent_stats 行"""
        battle_time = ctx.user_stats.last_battle_at
        if not battle_time or ctx.current_timestamp - battle_time > 7200:
            # 无有效战斗时间戳或时间过旧，不做近期计算
            return

        with sqlite_read_only(ctx.account_id) as cursor:
            for mode, ship_id, ship_data, old_entry in recent_ships:
                # 读取已有旧快照，用于计算各数据类型的差值
                old_data = None
                old_index = old_entry.index if old_entry else None
                if old_index is not None:
                    old_data = ShipDataRepository.read(cursor, ship_id, mode, old_index)
                    if old_data is None:
                        logger.error(
                            f'{ctx.account_id} | Missing snapshot '
                            f'`{ship_id}-{mode.name}-{old_index}`'
                        )
                        continue

                for data_type in (DataType.SOLO, DataType.DIV2, DataType.DIV3):
                    new_sbs = ship_data.get_type_stats(data_type)
                    if new_sbs is None:
                        continue
                    new_list = new_sbs.to_list()
                    old_sbs = old_data.get_type_stats(data_type) if old_data else None
                    old_list = old_sbs.to_list() if old_sbs else [0] * 12

                    # 差值战斗场次 <= 0 表示该类型近期无战斗，跳过
                    delta_battles = new_list[0] - old_list[0]
                    if delta_battles <= 0:
                        continue
                    # 任一字段出现负差值则数据异常，跳过
                    deltas = [new - old for new, old in zip(new_list[1:], old_list[1:])]
                    if any(delta < 0 for delta in deltas):
                        continue

                    # 记录近期数据行
                    ctx.update_plan.user_recent.set_insert_params(
                        ship_id=ship_id, 
                        ship_mode=mode, 
                        data_type=data_type, 
                        battles=delta_battles, 
                        deltas=deltas, 
                        battle_time=battle_time
                    )
