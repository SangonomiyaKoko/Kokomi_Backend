import json
from collections import defaultdict

from shard import RatingUtils

from .logger import logger
from .settings import (
    BUCKETS,
    MIN_SAMPLES
)

# 字段索引常量（与 ship_cache 值数组顺序严格对应）
IDX_BATTLES       = 0
IDX_WINS          = 1
IDX_DAMAGE        = 2
IDX_FRAGS         = 3
IDX_EXP           = 4
IDX_SURVIVED      = 5
IDX_SCOUT_DMG     = 6  # 精度修正需 * 100
IDX_POTENTIAL_DMG = 7  # 精度修正需 * 1000

NUM_STATS = 8  # 原始统计数据字段数量

# ship_user_stats 数组中各字段的索引位置
IDX_USER_BATTLES        = 0   # 总战斗场次（所有有效用户累加）
IDX_USER_COUNT          = 1   # 有效用户数
IDX_USER_WINS           = 2   # 胜率总和
IDX_USER_DAMAGE         = 3   # 场均伤害总和
IDX_USER_FRAGS          = 4   # 场均击毁总和
IDX_USER_EXP            = 5   # 场均经验总和
IDX_USER_SURVIVED       = 6   # 存活率总和
IDX_USER_SCOUT_DMG      = 7   # 场均侦查伤害总和
IDX_USER_POTENTIAL_DMG  = 8   # 场均潜在伤害总和
IDX_USER_RATING_SUM     = 9   # Rating 总和


class HistogramBins:
    """
    固定桶宽直方图管理器
    
    负责管理 Rating 分布的桶划分、样本落桶以及从桶数组反向计算百分位数
    
    Attributes:
        bucket_count: 桶的数量
        min_val: 直方图覆盖的最小值
        max_val: 直方图覆盖的最大值
    """

    def __init__(self, bucket_count: int, min_val: float, max_val: float):
        """
        初始化直方图桶管理器
        
        Args:
            bucket_count: 桶的数量（必须 >= 2）
            min_val: 直方图覆盖的最小值（包含）
            max_val: 直方图覆盖的最大值（包含）
        """
        self.bucket_count = bucket_count
        self.min_val = min_val
        self.max_val = max_val
        # 计算每个桶的宽度
        self.bin_width = (max_val - min_val) / bucket_count

    def get_bucket(self, value: float) -> int:
        """
        根据数值计算其落入的桶索引
        
        桶索引从 0 到 bucket_count-1，索引越小对应的值越小
        小于等于 min_val 的值落入桶 0，大于等于 max_val 的值落入最后一个桶
        
        Args:
            value: 待分桶的数值
            
        Returns:
            桶索引（0 到 bucket_count-1）
        """
        if value <= self.min_val:
            return 0
        if value >= self.max_val:
            return self.bucket_count - 1
        return int((value - self.min_val) / self.bin_width)

    def compute_percentiles(self, bins: list[int], targets: list[float]) -> list[float]:
        """
        从桶数组计算指定百分位数
        
        算法说明：
            - 将桶数组视为从最小到最大的有序分布
            - 对于每个 target（如 0.01），计算对应的排名位置
            - target 的含义是"超越该比例玩家所需的最小值"
            - 例如 target=0.01 表示"超越 99% 玩家所需的最小值"，即第 99 百分位数
            - 在桶内使用线性插值提高精度
        
        Args:
            bins: 各桶的样本数量数组（索引 0 对应最小值区间，索引 bucket_count-1 对应最大值区间）
            targets: 要计算的百分位目标列表，例如 [0.01, 0.05, 0.10, 0.15, 0.50, 0.75, 0.90]
            
        Returns:
            与 targets 顺序对应的百分位数值列表，单位与 min_val/max_val 一致
        """
        total = sum(bins)
        if total == 0:
            return [0.0] * len(targets)

        # 计算每个 target 对应的样本排名位置（从 0 开始计数）
        # target 越小 → 排名越靠后（越接近最大值）
        # 例如 total=1000：
        #   0.01 → rank=990（即第 99 百分位，只有 1% 的玩家比这个值高）
        #   0.50 → rank=500（即第 50 百分位，中位数）
        #   0.90 → rank=100（即第 10 百分位，有 90% 的玩家比这个值高）
        target_ranks = {
            t: int((1.0 - t) * total) if t < 1.0 else total - 1
            for t in targets
        }

        cumulative = 0
        found = {}
        
        # 遍历每个桶，累计样本数，找到目标排名所在的桶
        for i, count in enumerate(bins):
            cumulative += count
            for t in list(target_ranks.keys()):
                if t not in found and cumulative > target_ranks[t]:
                    prev_cumulative = cumulative - count
                    rank = target_ranks[t]
                    # 在桶内进行线性插值
                    if count > 0:
                        fraction = (rank - prev_cumulative) / count
                    else:
                        fraction = 0
                    # 计算百分位数值：桶起始值 + 桶内偏移
                    found[t] = self.min_val + (i + fraction) * self.bin_width
                    # 所有 target 都已找到，提前退出
                    if len(found) == len(targets):
                        break
            if len(found) == len(targets):
                break

        # 返回按 targets 顺序排列的结果，未找到的 target 返回 min_val
        return [found.get(t, self.min_val) for t in targets]

class ShipStatsAggregator:
    """舰船服务器数据聚合类

    负责从原始用户缓存数据中聚合三类统计数据：
        1. 服务器场次平均数据（所有用户数据累加后求平均）
        2. 服务器用户平均数据（只统计 battles > 10 的有效用户）
        3. 用户 Rating 分布直方图（用于计算 Rating 百分位数）
        4. 统计船只持有率和用户平均场次所需要的数据
    """

    def __init__(self, server_ship_metrics: dict[int, list[float]]):
        """
        初始化舰船统计数据聚合器
        
        创建三个核心数据结构：
            - ship_stats: 存储所有用户的场次累加数据
            - ship_user_stats: 存储有效用户（battles > 10）的场均累加数据
            - ship_rating_hist: 存储 Rating 分布直方图
            - ship_ownership_stats: 存储船只持有用户数和总场次

        Args:
            server_ship_metrics: 服务器场次基准数据，用于计算 Rating
            格式：{ship_id: [win_rate, avg_damage, avg_frags]}
        """
        # 用于计算 Rating 的服务器数据
        self.server_ship_metrics = server_ship_metrics

        # 一：服务器场次平均数据（所有用户数据累加）
        # ship_id -> [battles, wins, damage, frags, exp, survived, scout_dmg, potential_dmg]
        self.ship_stats = defaultdict(lambda: [0] * NUM_STATS)

        # 二：服务器用户平均数据（只统计 battles > 10 的有效用户）
        # ship_id -> [battles, users, wins, damage, frags, exp, survived, scout_dmg, potential_dmg, rating_sum]
        # 初始化时 rating_sum 设为 -1，用于区分"无有效用户"和"有效用户 rating 总和为 0"
        self.ship_user_stats = defaultdict(lambda: [0] * (NUM_STATS + 1) + [-1])

        # 三：用户 Rating 分布直方图（只统计 battles > 10 且 rating >= 0 的用户）
        # 使用固定桶宽直方图，范围 [0, 10000]
        self.rating_bins = HistogramBins(bucket_count=BUCKETS, min_val=0, max_val=8000)
        # ship_id -> [bucket_0_count, bucket_1_count, ..., bucket_{BUCKETS-1}_count]
        self.ship_rating_hist = defaultdict(lambda: [0] * self.rating_bins.bucket_count)

        # 四：船只持有统计（所有有数据的用户）
        # ship_id -> [ship_users, total_battles]
        self.ship_ownership_stats = defaultdict(lambda: [0, 0])

        # Rating 百分位目标
        self.rating_percentile_targets = [0.01, 0.05, 0.10, 0.15, 0.50, 0.75, 0.90]

        # 简单计数器
        self.total_users = 0   # 累计处理的用户数
        self.total_ship_entries = 0   # 累计处理的船只-用户条目数
        self.total_ship_battles = 0   # 累计处理的总战斗场次

    def add_batch(self, rows: list[tuple]) -> None:
        """处理一批原始缓存数据，并累加到服务器统计与用户 Rating 分布中
        
        Args:
            rows: 数据库查询结果列表
        """

        for row in rows:
            if row is None:
                continue

            try:
                # 解析 JSON 格式的船只缓存数据
                payload = json.loads(row[0])
            except (json.JSONDecodeError, TypeError):
                continue

            if not isinstance(payload, dict):
                continue

            self.total_users += 1

            # 临时存储本用户的有效船只场均数据
            # ship_id -> [battles, win_rate, avg_damage, avg_frags, avg_exp, 
            #             avg_survived, avg_scout, avg_potential, rating]
            valid_user_averages = {}

            # 遍历该用户的每艘船的数据
            for ship_id_str, stats in payload.items():
                # 验证数据格式：必须是列表且长度至少为 NUM_STATS
                if not isinstance(stats, list) or len(stats) < NUM_STATS:
                    continue

                try:
                    ship_id = int(ship_id_str)
                except ValueError:
                    continue

                # 一：累加场次维度原始数据（所有用户）
                ship = self.ship_stats[ship_id]
                ship[IDX_BATTLES] += stats[IDX_BATTLES]
                ship[IDX_WINS] += stats[IDX_WINS]
                ship[IDX_DAMAGE] += stats[IDX_DAMAGE]
                ship[IDX_FRAGS] += stats[IDX_FRAGS]
                ship[IDX_EXP] += stats[IDX_EXP]
                ship[IDX_SURVIVED] += stats[IDX_SURVIVED]
                ship[IDX_SCOUT_DMG] += stats[IDX_SCOUT_DMG]
                ship[IDX_POTENTIAL_DMG] += stats[IDX_POTENTIAL_DMG]

                self.total_ship_entries += 1
                self.total_ship_battles += stats[IDX_BATTLES]

                # 四：累加船只持有统计（所有有数据的用户）
                # ship_users 计数 +1（每个用户在同一船上只计一次）
                # total_battles 累加该用户在该船上的场次
                owner = self.ship_ownership_stats[ship_id]
                owner[0] += 1                    # 用户数 +1
                owner[1] += stats[IDX_BATTLES]   # 累加场次

                # 二：计算有效用户的场均数据（battles > 10）
                battles = stats[IDX_BATTLES]
                if battles > 10:
                    # 计算用户的场均指标
                    win_rate = stats[IDX_WINS] / battles
                    avg_damage = stats[IDX_DAMAGE] / battles
                    avg_frags = stats[IDX_FRAGS] / battles
                    
                    # 计算该用户在该船上的 Rating
                    rating = RatingUtils.calc_ship_rating(
                        ship_data=[
                            round(win_rate * 100, 4),     # 胜率转换为百分比
                            int(avg_damage),               # 场均伤害
                            round(avg_frags, 2)            # 场均击毁
                        ],
                        server_data=self.server_ship_metrics.get(ship_id)  # 基准数据（服务器平均）
                    )[0]
                    
                    valid_user_averages[ship_id] = [
                        battles,                                    # 战斗场次
                        win_rate,                                   # 胜率
                        avg_damage,                                 # 场均伤害
                        avg_frags,                                  # 场均击毁
                        stats[IDX_EXP] / battles,                   # 场均经验
                        stats[IDX_SURVIVED] / battles,              # 存活率
                        stats[IDX_SCOUT_DMG] / battles,             # 场均侦查伤害
                        stats[IDX_POTENTIAL_DMG] / battles,         # 场均潜在伤害
                        rating                                      # 玩家评分
                    ]

                    # 三：Rating 落桶（只统计 rating >= 0）
                    if rating >= 0:
                        bucket = self.rating_bins.get_bucket(rating)
                        self.ship_rating_hist[ship_id][bucket] += 1
            
            # 累加有效用户的场均数据到 ship_user_stats
            for ship_id, avgs in valid_user_averages.items():
                ship = self.ship_user_stats[ship_id]
                ship[IDX_USER_BATTLES] += avgs[0]       # 累加战斗场次
                ship[IDX_USER_COUNT] += 1                # 有效用户数 +1
                ship[IDX_USER_WINS] += avgs[1]           # 累加胜率
                ship[IDX_USER_DAMAGE] += avgs[2]         # 累加场均伤害
                ship[IDX_USER_FRAGS] += avgs[3]          # 累加场均击毁
                ship[IDX_USER_EXP] += avgs[4]            # 累加场均经验
                ship[IDX_USER_SURVIVED] += avgs[5]       # 累加存活率
                ship[IDX_USER_SCOUT_DMG] += avgs[6]      # 累加场均侦查伤害
                ship[IDX_USER_POTENTIAL_DMG] += avgs[7]  # 累加场均潜在伤害
                # 只有 rating >= 0 才累加到总和（保持与直方图一致）
                # sentinel 值为 -1，第一个有效 rating 需直接赋值以跳过 sentinel
                if avgs[8] >= 0:
                    if ship[IDX_USER_RATING_SUM] == -1:
                        ship[IDX_USER_RATING_SUM] = avgs[8]
                    else:
                        ship[IDX_USER_RATING_SUM] += avgs[8]

    def compute_battle_averages(self, ship_ids: list[int]) -> dict:
        """计算每艘船的服务器场次平均数据
        
        将累加的所有用户原始数据按总场次求平均，得到服务器级别的场均指标
        
        Args:
            ship_ids: 需要计算平均值的船只 ID 列表（用于过滤）
            
        Returns:
            字典，键为 ship_id，值为平均数据列表：
            [total_battles, win_rate(%), avg_damage, avg_frags, avg_exp, 
             survived_rate(%), scouting_dmg, potential_dmg]
        """
        averages = {}
        for ship_id, ship in self.ship_stats.items():
            if ship_id not in ship_ids:
                continue

            total_battles = ship[IDX_BATTLES]
            if total_battles == 0:
                continue

            averages[ship_id] = [
                total_battles,                                         # 总战斗场次
                round(ship[IDX_WINS] / total_battles * 100, 2),        # 胜率（%）
                round(ship[IDX_DAMAGE] / total_battles, 1),            # 场均伤害
                round(ship[IDX_FRAGS] / total_battles, 2),             # 场均击毁
                round(ship[IDX_EXP] / total_battles, 2),               # 场均经验
                round(ship[IDX_SURVIVED] / total_battles * 100, 2),    # 存活率（%）
                int(ship[IDX_SCOUT_DMG] * 100 / total_battles),        # 场均侦查伤害
                int(ship[IDX_POTENTIAL_DMG] * 1000 / total_battles)    # 场均潜在伤害
            ]
        return averages
    
    def compute_user_averages(self, ship_ids: list[int]) -> dict:
        """计算每艘船的用户平均数据
        
        将有效用户（battles > 10）的场均数据按用户数求平均，得到用户在该船上的平均表现
        
        Args:
            ship_ids: 需要计算平均值的船只 ID 列表（用于过滤）
            
        Returns:
            字典，键为 ship_id，值为平均数据列表：
            [battles, users, avg_rating, win_rate(%), avg_damage, avg_frags, 
             avg_exp, survived_rate(%), avg_scouting_dmg, avg_potential_dmg]
        """
        averages = {}
        for ship_id, ship in self.ship_user_stats.items():
            if ship_id not in ship_ids:
                continue

            users = ship[IDX_USER_COUNT]
            if users == 0:
                continue
                
            # 计算平均 Rating
            if ship[IDX_USER_RATING_SUM] == -1:
                rating = -1  # 无有效 Rating 用户
            else:
                rating = int(ship[IDX_USER_RATING_SUM] / users)
                
            averages[ship_id] = [
                ship[IDX_USER_BATTLES],                                 # 总战斗场次
                users,                                                  # 有效用户数
                rating,                                                 # 用户平均 Rating
                round(ship[IDX_USER_WINS] * 100 / users, 2),           # 用户平均胜率（%）
                round(ship[IDX_USER_DAMAGE] / users, 1),               # 用户平均场均伤害
                round(ship[IDX_USER_FRAGS] / users, 2),                # 用户平均场均击毁
                round(ship[IDX_USER_EXP] / users, 2),                  # 用户平均场均经验
                round(ship[IDX_USER_SURVIVED] * 100 / users, 2),       # 用户平均存活率（%）
                int(ship[IDX_USER_SCOUT_DMG] * 100 / users),           # 用户平均场均侦查伤害
                int(ship[IDX_USER_POTENTIAL_DMG] * 1000 / users)       # 用户平均场均潜在伤害
            ]
        return averages

    def compute_rating_percentiles(self) -> dict:
        """计算各船只的 Rating 百分位分布数据
        
        从直方图桶数组中计算出各百分位数，用于描述 Rating 的分布特征
        只计算样本数 >= MIN_SAMPLES 的船只
        
        Returns:
            字典，键为 ship_id，值为分布数据列表：
            [sample_count, top1, top5, top10, top15, top50, top75, top90]
            其中 topN 表示前 N% 的 Rating 阈值（四舍五入取整）
        """
        percentiles = {}
        for ship_id, bins in self.ship_rating_hist.items():
            total = sum(bins)
            # 样本数不足，跳过
            if total < MIN_SAMPLES:
                continue
                
            # 从直方图计算百分位数
            pvals = self.rating_bins.compute_percentiles(bins, self.rating_percentile_targets)
            
            # 返回 [sample_count, top1%, top5%, top10%, top15%, top50%, top75%, top90%]
            # 共 8 个值（对应数据库表 T_ship_rating_distribution 的字段）
            percentiles[ship_id] = [total] + [round(p) for p in pvals]
            
        return percentiles
    
    def compute_ownership_stats(self, ship_ids: list[int]) -> list:
        """计算每艘船的持有统计更新数据
        
        将累加的船只持有用户数和总场次转换为待数据库更新的元组列表，
        排除异常 ship_id 和无效数据
        
        Args:
            ship_ids: 有效的船只 ID 列表（用于过滤）
            
        Returns:
            待更新数据列表，每项为 [ship_users, total_battles, ship_id]
        """
        update_data = []
        for ship_id, owner in self.ship_ownership_stats.items():
            if ship_id not in ship_ids:
                continue
            
            ship_users = owner[0]
            total_battles = owner[1]
            
            if ship_users == 0:
                continue
            
            update_data.append([ship_users, total_battles, ship_id])
        
        return update_data

    def aggregation_stats(self) -> tuple[int, int, int]:
        """输出聚合统计概要到日志

        将本轮聚合处理的用户数、船只条目数和总战斗场次写入 INFO 日志，
        并以元组形式返回，供 refresh_table_meta 写入 T_table_meta 表。

        Returns:
            (total_users, total_ship_entries, total_ship_battles)
        """
        logger.info(
            "Users: %s | "
            "Ship Entries: %s | "
            "Total Battles: %s",
            f"{self.total_users:,}",
            f"{self.total_ship_entries:,}",
            f"{self.total_ship_battles:,}"
        )
        return (self.total_users, self.total_ship_entries, self.total_ship_battles)