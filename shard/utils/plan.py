import heapq
from typing import Optional

from .time import TimeUtils
from .scheduler import SchedulerUtils
from ..contracts import CommonConfig


MIN_IMBALANCE_SCORE = 20

class DueEntityContainer:
    """容量固定的到期实体容器，用于筛选本轮需要派发的实体

    堆内元素为 (priority, -entity_id)：同优先级的实体中 ID 较小者键更大，会被优先保留
    """

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity  # 可储存的最大实体数量
        self._heap: list[tuple[int, int]] = []

    def offer(self, due_entities: dict[int, int]) -> None:
        """接收一批 {entity_id: priority} 形式的到期实体"""
        capacity = self.capacity
        if capacity <= 0:
            return

        heap = self._heap
        for entity_id, priority in due_entities.items():
            # entity_id 取负是为了让 ID 较小的实体在最小堆中表现为较大的键
            key = (priority, -entity_id)
            if len(heap) < capacity:
                heapq.heappush(heap, key)
            elif key > heap[0]:
                # 堆顶即容器内优先级最低的实体，直接剔除堆顶并写入新实体
                heapq.heapreplace(heap, key)
            # 入队失败直接丢弃

    def get_entity_ids(self) -> list[int]:
        """按优先级从高到低返回容器内的实体 ID，同优先级按 ID 升序"""
        return [-key[1] for key in sorted(self._heap, reverse=True)]

    def __len__(self) -> int:
        return len(self._heap)


class RunCounter:
    """刷新计划的更新计数器

    due / no_due 由 RefreshPlanStats.add_batch 依据原始行累加，
    locked / pending 由调用方（调度 worker）自行赋值
    """

    def __init__(self) -> None:
        self.due = 0      # 所有已到期实体数
        self.no_due = 0   # 所有未到期实体数
        self.locked = 0   # 已在队列中等待更新的实体数
        self.pending = 0  # 本次更新计划传入队列实体数

    @property
    def waiting(self) -> int:
        """到期等待更新但本次未入队列的等待实体数"""
        return max(self.due - self.locked - self.pending, 0)

    def add_pending(self, pending) -> None:
        self.pending = pending


class RefreshPlanStats:
    """刷新计划的统计与均衡计算（用户与公会两侧共用）

    调用方逐批送入原始行，收集本批到期实体，最后做一次削峰重均衡：

    ```
        plan = RefreshPlanStats(
            ......
        )
        due = plan.add_batch(rows)   # {entity_id: priority}
        plan.rebalance_plan()        # 就地调整桶，迁移记录进入 to_db_data()
        plan.to_db_data()            # 写入数据库的统计字典
    ```
    """

    def __init__(
        self,
        advance_seconds: int,
        never_refreshed_priority: int,
        distribution_len: int
    ) -> None:
        # 调度参数由调用方注入，公用库不耦合具体服务的配置来源
        self._advance_seconds = advance_seconds
        self._never_refreshed_priority = never_refreshed_priority

        self.counter = RunCounter()

        self._remained_counts = 0  # 今日剩余计划更新实体数
        self._remained_seconds = TimeUtils.seconds_until_end_of_day()
        self._timestamp = TimeUtils.timestamp()

        # 未到期实体的刷新分布概览
        self._status = [0] * len(CommonConfig.STATUS_FIELDS)

        # 计划实体的 activity_level 分布，0-9
        self._distribution = [0] * distribution_len

        # 24H 内实体刷新分布概览
        self._buckets_capacity = 0  # _buckets 中实体总数
        self._buckets: list[list[int]] = [[] for _ in range(24)]

        # 重均衡产生的迁移列表，元素为 (hours, entity_id)
        self._migrations: list[tuple[int, int]] = []

    @property
    def planned_counts(self) -> int:
        # 计划更新用户总数 = 总用户数 - 不可用用户数
        return self._planned_counts

    @property
    def bucket_counts(self) -> list[int]:
        # 按桶顺序返回
        return [len(bucket) for bucket in self._buckets]

    @property
    def today_remained_counts(self) -> int:
        return self._remained_counts

    @property
    def migrations(self) -> int:
        return len(self._migrations)

    def _evaluate_row(
        self, next_refresh_at: Optional[int], updated_at: Optional[int]
    ) -> tuple[int, Optional[int]]:
        """判定一行的到期状态，返回 (remaining_seconds, update_priority)

        remaining_seconds 为 -1 表示已到期；update_priority 为 None 表示未到期
        """
        if updated_at is None:
            # 即使用户隐藏战绩也会刷新 updated_at
            # updated_at 为空说明该实体数据从未更新过，一并按逾期处理
            return -1, self._never_refreshed_priority

        if next_refresh_at is None:
            # 理论上不存在 updated_at 不为空但没有计划刷新时间的情况
            # 仅 is_enabled = 0 的不可用实体没有更新计划，但此处应当不可达
            return -1, self._never_refreshed_priority

        if self._timestamp >= next_refresh_at - self._advance_seconds:
            # 提前 advance_seconds 就准备刷新
            if self._timestamp > next_refresh_at:
                # 已到期实体按过期时间设置优先级，确保先到期者先更新
                return -1, self._timestamp - next_refresh_at

            # 提前刷新时优先级统一设置为 0
            return -1, 0

        # 未到期实体计算剩余时间，用于统计未来更新计划
        return next_refresh_at - self._timestamp, None

    def add_batch(self, rows: tuple) -> dict[int, int]:
        """处理一批原始行，返回本批到期实体的 {entity_id: priority}"""
        due_ids: dict[int, int] = {}

        for row in rows:
            entity_id, is_enabled, activity_level, next_refresh_at, updated_at = row
            if not is_enabled:
                # 直接抛弃不可用实体，不计入计划更新数
                continue

            # 统计实体的活跃等级分布，初始化阶段会将所有实体写入 0 中
            self._distribution[activity_level] += 1

            remaining_seconds, update_priority = self._evaluate_row(
                next_refresh_at=next_refresh_at,
                updated_at=updated_at
            )

            # 统计到今天结束前还剩余的计划更新数，仅用于日志输出，不写入数据库
            # 注意：此处的“今天”指服务器本地时区，写入数据库的数据一律采用 UTC 时间
            if remaining_seconds < self._remained_seconds:
                self._remained_counts += 1

            # 已到期实体
            if update_priority is not None:
                self._status[0] += 1  # overdue

                self._buckets[0].append(entity_id)  # 已到期实体同样写入 hour = 0 的桶
                self._buckets_capacity += 1
                
                due_ids[entity_id] = update_priority
                self.counter.due += 1
                continue

            # 未到期实体
            self.counter.no_due += 1

            # status 分类
            if remaining_seconds <= 86400:
                self._status[1] += 1  # within_24h
            elif remaining_seconds <= 604800:
                self._status[2] += 1  # within_week
            elif remaining_seconds <= 2592000:
                self._status[3] += 1  # within_month
            elif remaining_seconds <= 7776000:
                self._status[4] += 1  # within_quarter

            # hourly bucket
            if remaining_seconds < 86400:
                # 按剩余小时放入对应的桶中
                hour_index = remaining_seconds // 3600
                if hour_index < 24:
                    self._buckets[hour_index].append(entity_id)
                    self._buckets_capacity += 1

        return due_ids

    def rebalance_plan(self) -> None:
        """基于当前 buckets 执行刷新计划的重均衡，就地调整桶内实体"""
        # 计算当前分布的逆增分数，如果超过阈值则需要进行负载平衡
        score = SchedulerUtils.calc_imbalance_score(self.bucket_counts)
        if not score >= MIN_IMBALANCE_SCORE:
            return

        min_peak_abs = max(100, self._buckets_capacity // 10000 * 100)
        min_interval_total = 2 * min_peak_abs

        # 查找需要重新分配的区间
        intervals = SchedulerUtils.find_rebalance_intervals(
            counts=self.bucket_counts,
            min_score=MIN_IMBALANCE_SCORE,
            min_peak_abs=min_peak_abs,
            min_interval_total=min_interval_total
        )
        if not intervals:
            return

        for left, right in intervals:
            # rebalance_interval 会就地修改桶内实体，因此切片外的桶不受影响
            bucket_slice = self._buckets[left:right + 1]
            migration = SchedulerUtils.rebalance_interval(bucket_slice)
            self._migrations.extend(migration)

        return

    def to_db_data(self) -> dict:
        """返回用于写入数据库的统计数据字典，包含：
            - refresh_stats    # [(status, count),...]
            - distribution     # [(count, level),...]
            - hourly_counts    # [(hour, counts),...]
            - all_migrations   # [(hours, entity_id),...]
        """
        refresh_status = [
            (count, status)
            for status, count in zip(
                CommonConfig.STATUS_FIELDS,
                self._status
            )
        ]

        distribution = [
            (count, level)
            for level, count in enumerate(self._distribution)
        ]

        hourly_counts = [
            (len(bucket), hour + 1)
            for hour, bucket in enumerate(self._buckets)
        ]

        return {
            'distribution': distribution,
            'refresh_stats': refresh_status,
            'hourly_counts': hourly_counts,
            'all_migrations': self._migrations
        }
