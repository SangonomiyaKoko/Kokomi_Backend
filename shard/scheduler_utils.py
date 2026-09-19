import math


class SchedulerUtils:
    """刷新计划调度与均衡相关公用函数"""

    @staticmethod
    def calc_imbalance_score(counts: list) -> float:
        """计算分布不合理系数

        定义为所有违反单调不增的相邻逆增量总和 / 区间总计划数 × 100
        返回值越接近 100 表示分布越不合理（越不满足单调不增）
        """
        n = len(counts)
        if n < 2:
            return 0.0

        total_excess = sum(
            max(0, counts[i + 1] - counts[i])
            for i in range(n - 1)
        )
        total = sum(counts)
        if total == 0:
            return 0.0

        return round((total_excess / total) * 100, 2)

    @staticmethod
    def find_rebalance_intervals(
        counts: list,
        min_score: float,
        min_peak_abs: int = 100,
        min_interval_total: int = 200
    ) -> list[tuple[int, int]]:
        """扫描 24 小时分布，返回需要削峰的区间

        一个合理的分布应为单调不增（越早时段更新越多）。本函数从后向前扫描，
        识别出右侧高、左侧低的“尖峰”区间，并按绝对数量与波动程度过滤
        """
        if len(counts) != 24:
            return []

        intervals = []
        hour = 23

        while hour > 0:
            # 跳过绝对数量过小
            if counts[hour] < min_peak_abs:
                hour -= 1
                continue

            # 未违反单调不增
            if counts[hour - 1] >= counts[hour]:
                hour -= 1
                continue

            # 向左寻找区间左边界：直到遇到第一个大于当前峰值的桶或到头
            left = hour - 1
            while left > 0:
                if counts[left - 1] < counts[hour]:
                    left -= 1
                else:
                    break

            interval_counts = counts[left: hour + 1]

            # 过滤总量过小
            if sum(interval_counts) < min_interval_total:
                hour = left - 1
                continue

            # 过滤轻微波动
            score = SchedulerUtils.calc_imbalance_score(interval_counts)
            if score >= min_score:
                intervals.append((left, hour))

            hour = left - 1

        return intervals

    @staticmethod
    def rebalance_interval(buckets_slice: list) -> list[tuple[int, int]]:
        """对区间内的桶做负载均衡（只能提前，就近填谷）

        从最左侧桶开始，若低于目标平均值，则从右侧最近的富余桶借用元素。
        返回所有需要提前的迁移记录 [(entity_id, advance_hours), ...]
        """
        n = len(buckets_slice)
        if n <= 1:
            return []

        # 每桶当前元素数
        counts = [len(bucket) for bucket in buckets_slice]
        total = sum(counts)
        target = math.floor(total / n)
        if target == 0 and total > 0:
            target = 1  # 至少填至 1，避免永远填不满

        migrations = []

        for i in range(n):
            deficit = target - counts[i]
            if deficit <= 0:
                continue

            j = i + 1
            while deficit > 0 and j < n:
                surplus = counts[j] - target
                if surplus > 0:
                    move = min(deficit, surplus)
                    # 从桶 j 取出 move 个元素，放入桶 i
                    for _ in range(move):
                        if not buckets_slice[j]:
                            break
                        entity_id = buckets_slice[j].pop()
                        buckets_slice[i].append(entity_id)
                        migrations.append((j - i, entity_id))
                    counts[i] += move
                    counts[j] -= move
                    deficit -= move
                j += 1

        # 注意：因取整可能导致极少元素未被分配，留在原桶不影响整体合理性
        return migrations
