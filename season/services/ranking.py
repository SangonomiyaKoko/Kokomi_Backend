import msgpack

from shard import RedisKeys, TimeUtils

from ..core import RunContext
from ..db_ops import mysql_read_only
from ..repository import ClanStatsRepository
from ..logger import logger
from ..settings import DATA_DIR


# 快照中记录的公会数量上限
TOP_CLAN_LIMIT = 50


class ClanRankingWriter:
    """生成公会排行榜快照文件，供主节点同步"""

    @classmethod
    def main(cls, run_ctx: RunContext) -> None:
        """读取排行榜前 N 名并写入 msgpack 快照"""
        # 先读取目前缓存中所有工会的数量
        ranking_key = RedisKeys.clan_zrank()
        total_clans = run_ctx.redis_client.zcard(ranking_key)
        if total_clans == 0:
            logger.info('Clan ranking is empty, snapshot skipped')
            return

        # 获取的 total_clans 不为 0 则说明获取到的 clans 不会为 None
        clans = run_ctx.redis_client.zrevrange(
            ranking_key, 0, TOP_CLAN_LIMIT - 1
        )

        # 从 MySQL 读取各个工会具体的排名数据
        with mysql_read_only(run_ctx.mysql_connection) as cursor:
            rows = ClanStatsRepository.load_leaderboard(cursor, clans)

        data = []
        for clan_id in clans:
            row = rows.get(clan_id)
            if row is None:
                # 此处不应该出现在 Redis 中存在 key 而 MySQL 中不存在的情况
                # 为确保数据的准确性本次更新不刷新缓存文件，删除 key 由下次更新处理
                run_ctx.redis_client.zrem(RedisKeys.clan_zrank(), str(clan_id))
                logger.error(f'Table missing: T_clan_stats - {clan_id}')
                return
            
            # 名次按实际写入的行数连续编排
            data.append([len(data) + 1, int(clan_id)] + row)

        payload = {
            'time': TimeUtils.timestamp(),
            'season': run_ctx.season_id,
            'clans': total_clans,   # 所有上榜工会数量
            'data': data            # 仅需要保存 TOP_50 的工会
        }

        file_path = DATA_DIR / 'local/clan_ranking.msgpack'
        packed_bytes = msgpack.packb(payload, use_bin_type=True)
        with open(file_path, "wb") as f:
            f.write(packed_bytes)
