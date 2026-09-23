import json
import zlib

from typing import Optional

from shard import CommonConfig, LevelAlgo


# 船只记录值字段，顺序与 T_ship_record 的列一致
FIELDS = ('exp', 'frags', 'planes', 'damage', 'scouting', 'potential')
SHIP_COLUMNS = len(FIELDS) + 1  # ship_id + FIELDS


class ShipRecordUpdater:
    """船只记录值（各指标历史最大值）的比对器"""

    def __init__(self, rows) -> None:
        """rows 为数据库查询结果，列顺序必须是 ship_id + FIELDS。"""
        self.records = {
            row[0]: list(row[1:SHIP_COLUMNS])
            for row in rows
        }
        self._updates: dict[int, tuple] = {}

    def compare(self, ship_id: int, ship_data) -> bool:
        """传入船只 id 和该船数据（按 FIELDS 顺序），返回是否有字段变大。

        ship_id 不在初始化数据里则直接跳过；有字段变大时更新缓存并标记该船。
        """
        record = self.records.get(ship_id)
        if record is None:
            return False

        values = list(ship_data)[:len(FIELDS)]
        if not any(new > old for new, old in zip(values, record)):
            return False

        record = [max(new, old) for new, old in zip(values, record)]
        self.records[ship_id] = record
        self._updates[ship_id] = (*record, ship_id)
        return True

    def output(self) -> list[tuple]:
        """返回被标记船只的更新参数：(exp, ..., potential, ship_id)。"""
        return list(self._updates.values())


# 服务端均值有效所需的最小样本场次
SERVER_SAMPLE_LIMIT = 1000

BENCHMARK_COLUMNS = 6  # ship_id + tier + battles + (win_rate, avg_damage, avg_frags)


class ShipBenchmark:
    """船只基准数据缓存，列为 ship_id + tier + battles + 三项服务端均值

    直接读 T_ship_base 与 T_ship_stats_by_battles，不走 V_ship_ranking_stats：
    后者固定了船只过滤条件与场次门槛，而本服务需要按 tier 自行判定能否上榜。
    服务端样本场次不足时 server_stats 返回 None，此时无法计算 Rating。
    """

    def __init__(self, rows) -> None:
        self._rows = {
            row[0]: (row[1], row[2], tuple(row[3:BENCHMARK_COLUMNS]))
            for row in rows
        }

    def tier(self, ship_id: int) -> Optional[int]:
        """该船的舰种等级，不在启用集合中时返回 None。"""
        row = self._rows.get(ship_id)
        return None if row is None else row[0]

    def min_battles(self, ship_id: int) -> Optional[int]:
        """该船计入榜单所需的最少场次，不参与排行的等级返回 None。"""
        tier = self.tier(ship_id)
        if tier is None:
            return None

        return CommonConfig.RANKING_BATTLES_LIMIT.get(tier)

    def server_stats(self, ship_id: int) -> Optional[tuple]:
        """该船的服务端均值 (win_rate, avg_damage, avg_frags)，样本不足时返回 None。"""
        row = self._rows.get(ship_id)
        if row is None or row[1] < SERVER_SAMPLE_LIMIT:
            return None

        return row[2]


# 单船数据字段，pvp 总计在前，solo 总计在后
PVP_FIELDS = (
    'battles', 'wins', 'damage', 'frags',
    'exp', 'survived', 'scouting', 'potential'
)
SOLO_FIELDS = (
    'solo_battles', 'solo_wins', 'solo_damage',
    'solo_frags', 'solo_exp', 'solo_survived'
)
SHIP_FIELDS = PVP_FIELDS + SOLO_FIELDS
PAYLOAD_COLUMNS = len(SHIP_FIELDS) + 1  # ship_id + SHIP_FIELDS

# 记录值取自 pvp 数据，顺序与 FIELDS 一致
RECORD_KEYS = (
    'max_exp', 'max_frags', 'max_planes_killed',
    'max_damage_dealt', 'max_scouting_damage', 'max_total_agro'
)


class ShipCacheData:
    """单个用户的船只数据，同时负责 payload 的编解码

    payload 采用列式存储：[[ship_id...], [battles...], ..., [solo_survived...]]，
    同一字段的值连续存放，配合 zlib 压缩比按船分行的结构更紧凑。
    """

    def __init__(
        self,
        ships: dict,
        records: dict = None,
        hit_ratios: dict = None
    ) -> None:
        self.ships = ships            # {ship_id: [SHIP_FIELDS 顺序的 14 个值]}
        self.records = records or {}  # {ship_id: [FIELDS 顺序的 6 个最大值]}
        self.hit_ratios = hit_ratios or {}   # {ship_id: 命中率}

    @classmethod
    def parse(
        cls, responses: list, account_id: int
    ) -> 'ShipCacheData':
        """解析 pvp 与 pvp_solo 两个接口的响应"""
        pvp_statistics = responses[0].get(str(account_id), {}).get('statistics', {})
        solo_statistics = responses[1].get(str(account_id), {}).get('statistics', {})

        ships = {}
        records = {}
        hit_ratios = {}
        for ship_key, ship_data in pvp_statistics.items():
            # 接口返回的键为字符串，统一转为整型以便与数据库数据比对
            if not str(ship_key).isdigit():
                continue

            ship_id = int(ship_key)
            pvp = ship_data.get('pvp', {})
            if not pvp:
                continue

            solo = solo_statistics.get(ship_key, {}).get('pvp_solo', {})
            ships[ship_id] = [
                pvp.get('battles_count', 0),
                pvp.get('wins', 0),
                pvp.get('damage_dealt', 0),
                pvp.get('frags', 0),
                pvp.get('original_exp', 0),
                pvp.get('survived', 0),
                # 侦查与潜在伤害在缓存中按百位、千位存放，比较与写入时需要还原
                max(pvp.get('assist_damage', 0), pvp.get('scouting_damage', 0)) // 100,
                pvp.get('art_agro', 0) // 1000,
                solo.get('battles_count', 0),
                solo.get('wins', 0),
                solo.get('damage_dealt', 0),
                solo.get('frags', 0),
                solo.get('original_exp', 0),
                solo.get('survived', 0)
            ]
            records[ship_id] = [pvp.get(key, 0) for key in RECORD_KEYS]

            shots = pvp.get('shots_by_main', 0)
            hits = pvp.get('hits_by_main', 0)
            hit_ratios[ship_id] = round(hits / shots * 100, 2) if shots else 0

        return cls(ships=ships, records=records, hit_ratios=hit_ratios)

    @classmethod
    def unpack(cls, payload: Optional[bytes]) -> 'ShipCacheData':
        """解压 payload，无本地数据时返回空实例"""
        if not payload:
            return cls(ships={})

        columns = json.loads(zlib.decompress(payload))
        ship_ids = columns[0]
        ships = {
            ship_id: [
                columns[i + 1][index]
                for i in range(len(SHIP_FIELDS))
            ]
            for index, ship_id in enumerate(ship_ids)
        }

        return cls(ships=ships)

    def pack(self) -> bytes:
        """按列打包并压缩为 payload"""
        ship_ids = list(self.ships.keys())
        columns = [ship_ids]
        for i in range(len(SHIP_FIELDS)):
            columns.append([values[i] for values in self.ships.values()])

        return zlib.compress(json.dumps(columns).encode('utf-8'))

    def changed_ships(self, old: 'ShipCacheData') -> dict:
        """返回与本地数据相比发生过变化的船只"""
        return {
            ship_id: values
            for ship_id, values in self.ships.items()
            if old.ships.get(ship_id) != values
        }

    def recent_diff(self, ship_id: int, old: 'ShipCacheData') -> Optional[list]:
        """返回该船 pvp 数据的近期增量，增量异常或无新增场次时返回 None

        侦查与潜在伤害还原为原始单位（与旧版暂存表的口径一致）；
        任一字段出现负增量说明本地缓存不可信，该船本次不计入近期数据。
        """
        new_values = self.ships[ship_id][:len(PVP_FIELDS)]
        old_values = old.ships.get(ship_id, [0] * len(PVP_FIELDS))

        diff = [new - old for new, old in zip(new_values, old_values)]
        diff[-2] = diff[-2] * 100
        diff[-1] = diff[-1] * 1000
        if any(value < 0 for value in diff):
            return None
        if diff[0] == 0:
            return None

        return diff

    def user_level(self, benchmark: ShipBenchmark) -> int:
        """按舰种等级加权的有效场次与胜率计算用户水平"""
        entries = []
        for ship_id, values in self.ships.items():
            tier = benchmark.tier(ship_id)
            if tier is None:
                continue

            # [tier, battles, wins]，battles 与 wins 取 pvp 总计
            entries.append([tier, values[0], values[1]])

        return LevelAlgo.calculate_user_level(entries)
