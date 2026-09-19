import heapq

from shard import SchedulerUtils, TimeUtils

from .logger import logger
from .settings import (
    REBALANCE_ENABLED,
    MIN_IMBALANCE_SCORE,
    NEVER_REFRESHED_PRIORITY,
    REFRESH_ADVANCE_SECONDS
)


STATUS_NAMES = ['overdue', 'within_24h', 'within_week', 'within_month', 'within_quarter']

class DueClanContainer:
    """容量固定的到期公会容器，用于筛选本轮需要处理的公会

    堆内元素为 (priority, -clan_id)：同优先级的公会中 clan_id 较小者键更大，会被优先保留
    """

    def __init__(self, capacity: int) -> None:
        self.capacity = capacity
        self._heap: list[tuple[int, int]] = []

    def offer(self, due_clans: dict[int, int]) -> None:
        """接收一批 {clan_id: priority} 形式的到期公会"""
        capacity = self.capacity
        if capacity <= 0:
            return

        heap = self._heap
        for clan_id, priority in due_clans.items():
            # clan_id 取负是为了让 ID 较小的公会在最小堆中表现为较大的键
            key = (priority, -clan_id)
            if len(heap) < capacity:
                heapq.heappush(heap, key)
            elif key > heap[0]:
                # 堆顶即容器内优先级最低的公会，直接剔除堆顶并写入新公会
                heapq.heapreplace(heap, key)

    def get_clan_ids(self) -> list[int]:
        """按优先级从高到低返回容器内的公会 ID，同优先级按 ID 升序"""
        return [-key[1] for key in sorted(self._heap, reverse=True)]

    def __len__(self) -> int:
        return len(self._heap)


class RefreshPlanStats:
    """负责公会刷新计划的统计与均衡计算"""

    def __init__(self) -> None:
        self._planned_counts = 0
        self._remained_counts = 0
        self._buckets_capacity = 0
        self._remained_seconds = TimeUtils.seconds_until_end_of_day()
        self._timestamp = TimeUtils.timestamp()

        # 累加统计
        self.today_remained_count = 0
        self.total_count = 0  # 进入 hourly 桶的总数
        self.total_due = 0

        # 未到期工会刷新分布概览
        self._status = [0] * len(STATUS_NAMES)

        # 计划工会的 activity_level 分布，0-9
        self._distribution = [0] * 10

        # 24H 内工会刷新分布概览
        self._buckets: list[list[int]] = [[] for _ in range(24)]

        # 重均衡产生的迁移列表，元素为 (account_id, hours)
        self._migrations: list[tuple[int, int]] = []

    def add_batch(self, rows: tuple) -> dict[int, int]:
        """处理一批原始行，返回本批到期公会的 {clan_id: priority}"""
        due_clans: dict[int, int] = {}

        for row in rows:
            clan_id, is_enabled, activity_level, next_refresh_at, updated_at = row
            if not is_enabled:
                continue
            self._planned_counts += 1
            self._distribution[activity_level] += 1

            remaining_seconds = -1
            update_priority = None
            # 计算剩余秒数，-1 表示已经逾期
            # updated_at 为空说明该公会从未被实际刷新过，一并按逾期处理
            if updated_at is None:
                update_priority = NEVER_REFRESHED_PRIORITY
            elif next_refresh_at is None:
                update_priority = NEVER_REFRESHED_PRIORITY
            elif self._timestamp >= next_refresh_at - REFRESH_ADVANCE_SECONDS:
                # 设置为提前 60s 刷新公会
                if self._timestamp > next_refresh_at:
                    update_priority = self._timestamp - next_refresh_at
                else:
                    update_priority = 0
            else:
                remaining_seconds = next_refresh_at - self._timestamp

            # 统计到今天结束前还剩余的计划更新数
            if remaining_seconds < self._remained_seconds:
                self.today_remained_count += 1

            # overdue
            if remaining_seconds == -1:
                due_clans[clan_id] = update_priority
                self._status[0] += 1
                self._buckets[0].append(clan_id)
                self._buckets_capacity += 1
                continue

            # refresh_stats 分类
            # within_24h / within_week / within_month / within_quarter
            if remaining_seconds <= 86400:
                self._status[1] += 1
            elif remaining_seconds <= 604800:
                self._status[2] += 1
            elif remaining_seconds <= 2592000:
                self._status[3] += 1
            elif remaining_seconds <= 7776000:
                self._status[4] += 1

            # hourly bucket
            if remaining_seconds < 86400:
                hour_index = remaining_seconds // 3600
                if hour_index < 24:
                    self._buckets[hour_index].append(clan_id)
                    self._buckets_capacity += 1

        self.total_due += len(due_clans)
        return due_clans

    def rebalance_plan(self) -> None:
        """基于当前 buckets 执行公会刷新计划的重均衡，结果存入 self.all_migrations，并更新桶的内容"""
        counts = [len(bucket) for bucket in self._buckets]
        score = SchedulerUtils.calc_imbalance_score(counts)

        if not (REBALANCE_ENABLED and score >= MIN_IMBALANCE_SCORE):
            logger.debug('No interval needs rebalancing')
            return

        min_peak_abs = max(100, self.total_count // 10000 * 100)
        min_interval_total = 2 * min_peak_abs

        intervals = SchedulerUtils.find_rebalance_intervals(
            counts,
            min_score=MIN_IMBALANCE_SCORE,
            min_peak_abs=min_peak_abs,
            min_interval_total=min_interval_total
        )

        if not intervals:
            logger.debug('No interval needs rebalancing')
            return

        logger.info('Found %d intervals to rebalance: %s', len(intervals), intervals)

        for left, right in intervals:
            # rebalance_interval 会就地修改桶内公会，因此切片外的桶不受影响
            bucket_slice = self._buckets[left:right + 1]
            migrations = SchedulerUtils.rebalance_interval(bucket_slice)
            self.all_migrations.extend(migrations)

            # 同步区间内的桶人数，供后续区间的判断使用
            for hour in range(left, right + 1):
                counts[hour] = len(self._buckets[hour])

        score = SchedulerUtils.calc_imbalance_score(counts)
        logger.debug('Rebalanced plan (%s): %s', score, counts)

    def get_db_update_data(self) -> dict:
        """返回用于写入数据库的统计数据字典，包含：
            - planned_count
            - refresh_stats
            - hourly_counts
            - all_migrations
            - activity_distribution
        """
        refresh_status = [
            (count, status) for status, count in zip(STATUS_NAMES, self._status)
        ]

        distribution = [
            (count, level) 
            for level, count in enumerate(self._distribution)
        ]

        hourly_counts = [
            (hour+1, len(bucket)) for hour, bucket in enumerate(self._buckets)
        ]
        return {
            'planned_count': self._planned_counts,
            'refresh_stats': refresh_status,
            'activity_distribution': distribution,
            'hourly_counts': hourly_counts,
            'all_migrations': self._migrations
        }
