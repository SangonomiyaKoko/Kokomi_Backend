import time
from typing import Optional
from datetime import datetime, timezone


TIMEZONE_OFFSET = 5

class ISOTimeString:
    """处理ISO时间字符串信息"""
    _string: str

    def __init__(self, time: str):
        self._string = time

    @property
    def iso(self) -> str:
        """返回 ISO 8601 格式字符串

        eg: 2026-09-10T07:54:46+00:00
        """
        return self._string

    @property
    def date(self) -> str:
        """返回字符串中 date 信息

        eg: 2026-09-10
        """
        return self._string[:10]

    @property
    def date_year(self) -> str:
        """返回字符串中 date 信息

        eg: 2026
        """
        return self._string[:4]

    @property
    def date_month(self) -> str:
        """返回字符串中 date 信息

        eg: 2026-09
        """
        return self._string[:7]

    @property
    def time(self) -> str:
        """返回字符串中 time 信息

        eg: 07:54:46
        """
        return self._string[11:19]

class TimeUtils:
    """时间处理相关公用函数"""

    @staticmethod
    def timestamp() -> int:
        """获取当前的时间戳"""
        return int(time.time())

    @staticmethod
    def log_time() -> str:
        """获取用于日志输出的当前日期格式化字符串"""
        # 返回的是服务器所在时区时间，而非 UTC 时间
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    @staticmethod
    def log_retain_days(days: int) -> list[str]:
        """获取需要保存的 log 文件日期列表"""
        date_list = []

        ts = int(time.time())
        for _ in range(days):
            date = datetime.fromtimestamp(
                timestamp=ts,
                tz=timezone.utc
            ).strftime("%Y-%m-%d")
            date_list.append(f'{date}.log')
            ts -= 86400

        return date_list

    @staticmethod
    def log_stamp() -> str:
        """获取 UTC 时区下用于文件命名的时间戳字符串，按字符串排序即按时间先后

        eg: 20260915T190302
        """
        return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')

    @staticmethod
    def iso_time() -> ISOTimeString:
        """获取 UTC 时区 ISO 格式下的当前时间"""
        iso_time = datetime.now(
            tz=timezone.utc
        ).isoformat(timespec='seconds')

        return ISOTimeString(iso_time)

    @staticmethod
    def reset_date(
        tz: int, timestamp: int
    ) -> int:
        """获取基于时区漂移和更新漂移重置的日期

        eg: 20260910
        """
        # 计算偏移时间戳：当前时间戳 + 时区偏移 - 更新偏移
        reset_timestamp = (
            timestamp
            + tz * 3600
            - TIMEZONE_OFFSET * 3600
        )

        # 以 UTC 时间为基准计算服务所需的当前时间
        strftime = datetime.fromtimestamp(
            timestamp=reset_timestamp,
            tz=timezone.utc
        ).strftime("%Y%m%d")

        return int(strftime)

    @staticmethod
    def reset_date_list(
        tz: int, timestamp: int, start_date: int
    ) -> list[int]:
        """获取服务器重置日期列表，返回从当前日期到指定日期的日期，从新到旧排列"""
        result = []
        for i in range(1000):   # 正常情况下不可能超过 1000 天，此处为避免死循环
            reset_timestamp = (
                timestamp
                - i * 86400
                + tz * 3600
                - TIMEZONE_OFFSET * 3600
            )
            strftime = int(
                datetime.fromtimestamp(
                    timestamp=reset_timestamp,
                    tz=timezone.utc
                ).strftime("%Y%m%d")
            )
            result.append(strftime)
            if strftime == start_date:
                break

        # 确保日期严格递减，从新到旧
        for i in range(len(result) - 1):
            if result[i] <= result[i + 1]:
                raise RuntimeError("Date list not in strictly decreasing order")

        return result

    @staticmethod
    def formtime_to_timestamp(formtime: str) -> int:
        """将 ISO 格式时间字符串转换为 Unix 时间戳"""
        return int(datetime.fromisoformat(formtime).timestamp())

    @staticmethod
    def seconds_until_end_of_day() -> int:
        """计算从当前时刻到今天 23:59:59 剩余的秒数"""
        now = datetime.now()
        end_of_day = now.replace(
            hour=23,
            minute=59,
            second=59,
            microsecond=0

        )
        return int((end_of_day - now).total_seconds())
