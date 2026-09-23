from dataclasses import dataclass
from typing import Optional

from redis import Redis
from httpx import AsyncClient
from pymysql import Connection

from shard import (
    MySQLOPS,
    RedisKeys,
    SQLiteOPS,
    RatingAlgo
)

from .logger import logger
from .models import (
    FIELDS,
    ShipBenchmark,
    ShipCacheData,
    ShipRecordUpdater
)
from .requester import APIRequester
from .db_ops import BasicDataRepository, VersionRepository
from .settings import (
    DATA_DIR,
    CREATE_SQL,
    LEADERBOARD_PREFIX
)


@dataclass(frozen=True)
class UpdateContext:
    """单轮更新共享的上下文"""

    mysql_conn: Connection
    redis_client: Redis
    async_client: AsyncClient
    records: ShipRecordUpdater
    benchmarks: ShipBenchmark
    version: Optional[str]
    version_start: Optional[int]


class ShipPvpRefresher:
    """单个用户的船只 PvP 缓存刷新执行器

    编排一次刷新的完整流程：取数 -> 解析 -> 对比本地缓存 -> 写入排行榜与记录值
    """

    @staticmethod
    def _build_leaderboard_row(
        ctx: UpdateContext,
        account_id: int,
        ship_id: int,
        latest: ShipCacheData
    ) -> Optional[list]:
        """构建单船的排行榜写入参数，未达到上榜条件时返回 None"""
        min_battles = ctx.benchmarks.min_battles(ship_id)
        values = latest.ships.get(ship_id)
        if min_battles is None or values is None:
            return None

        battles = values[0]
        if battles < min_battles:
            return None

        win_rate = values[1] / battles * 100
        solo_rate = values[8] / battles * 100
        avg_damage = values[2] / battles
        avg_frags = values[3] / battles
        avg_exp = values[4] / battles

        # 无服务端均值（样本场次不足）时无法计算 Rating，写入 -1 表示不参与排名
        server_stats = ctx.benchmarks.server_stats(ship_id)
        rating, _, _ = RatingAlgo.calc_ship_rating(
            ship_data=[round(win_rate, 4), int(avg_damage), round(avg_frags, 2)],
            server_data=server_stats
        )

        max_values = dict(zip(
            FIELDS,
            latest.records.get(ship_id, [0] * len(FIELDS))
        ))

        return [
            account_id,
            ship_id,
            battles,
            rating,
            round(win_rate, 4),
            round(solo_rate, 4),
            int(avg_damage),
            round(avg_frags, 2),
            int(avg_exp),
            latest.hit_ratios.get(ship_id, 0),
            max_values['exp'],
            max_values['damage']
        ]

    @classmethod
    async def refresh(cls, ctx: UpdateContext, account_id: int) -> bool:
        """刷新单个用户的船只缓存数据，返回是否完成（未完成时下轮重试）"""
        # 取数：无版本信息时无法计算近期数据，保持待更新状态等待下轮
        if not ctx.version:
            logger.info(f'{account_id} | Game version not found')
            return False

        access_token = ctx.redis_client.get(RedisKeys.user_ac_token(account_id))
        responses = await APIRequester.fetch(
            redis_client=ctx.redis_client,
            async_client=ctx.async_client,
            account_id=account_id,
            access_token=access_token
        )
        if not responses:
            logger.info(f'{account_id} | Failed to obtain data')
            return False

        latest = ShipCacheData.parse(responses=responses, account_id=account_id)

        # 读取本地缓存与更新时间戳
        with MySQLOPS.read_only(ctx.mysql_conn) as cursor:
            local = BasicDataRepository.get_user_ships(
                cursor=cursor,
                account_id=account_id
            )

        payload, updated_at = local if local else (None, None)
        cached = ShipCacheData.unpack(payload)

        # 仅刷新发生变化的船只
        changed_ships = latest.changed_ships(cached)
        leaderboard_rows = []
        for ship_id in changed_ships:
            row = cls._build_leaderboard_row(
                ctx=ctx,
                account_id=account_id,
                ship_id=ship_id,
                latest=latest
            )
            if row is not None:
                leaderboard_rows.append(row)

        # 比对记录值，被刷新的船只在轮末统一写库
        for ship_id, record_values in latest.records.items():
            ctx.records.compare(ship_id, record_values)

        # 近期数据需要「本版本内」的增量：本地缓存无时间戳或早于版本开始时间时
        # 差值跨越了版本，不计入版本库，但缓存与榜单仍然正常刷新
        record_recent = (
            updated_at is not None
            and ctx.version_start is not None
            and updated_at >= ctx.version_start
        )
        if not record_recent:
            logger.debug(f'{account_id} | Skip recent data')

        user_level = latest.user_level(ctx.benchmarks)

        with MySQLOPS.transaction(ctx.mysql_conn) as cursor:
            BasicDataRepository.upsert_ship_leaderboard(
                cursor=cursor,
                rows=leaderboard_rows
            )
            BasicDataRepository.update_user_ships(
                cursor=cursor,
                account_id=account_id,
                ship_count=len(latest.ships),
                user_level=user_level,
                payload=latest.pack()
            )

        # 榜单缓存与版本库在事务提交后写入：版本库写入失败只是少记一次增量，
        # 而先写版本库再回滚事务会导致增量重复累加
        cls._update_redis(ctx, leaderboard_rows)
        if record_recent:
            cls._update_version_stats(ctx, latest, cached, changed_ships)

        return True

    @staticmethod
    def _update_redis(ctx: UpdateContext, rows: list) -> None:
        """刷新 Redis 中的船只榜单"""
        try:
            pipe = ctx.redis_client.pipeline()
            for row in rows:
                rating = row[3]
                if rating <= 0:
                    continue

                key = f'{LEADERBOARD_PREFIX}:ship:{row[1]}'
                pipe.zadd(key, {str(row[0]): rating})
            pipe.execute()
        except Exception as e:
            logger.error(f'Refresh redis failed: {type(e).__name__}')

    @staticmethod
    def _update_version_stats(
        ctx: UpdateContext,
        latest: ShipCacheData,
        cached: ShipCacheData,
        changed_ships: dict
    ) -> None:
        """将本轮变化量累加到当前版本的 SQLite 数据库"""
        version_file = SQLiteOPS.version_db_path(DATA_DIR, ctx.version)
        if not SQLiteOPS.ensure_database(version_file, CREATE_SQL):
            logger.error(f'SQLite database file is abnormal: {version_file.name}')
            return

        try:
            with SQLiteOPS.transaction(version_file) as cursor:
                for ship_id in changed_ships:
                    diff = latest.recent_diff(ship_id, cached)
                    if diff is None:
                        continue

                    VersionRepository.add_recent_stats(
                        cursor=cursor,
                        ship_id=ship_id,
                        diff=diff
                    )
        except Exception as e:
            logger.error(f'Update version stats failed: {type(e).__name__}')
