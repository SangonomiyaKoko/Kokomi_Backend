import time
from functools import wraps
from datetime import datetime, timezone
from typing import Optional, List

from app.core import EnvConfig, api_logger

# Recent服务重置时间是所在地区的 5:00 AM
SERVER_RESET_OFFSET = 5

class TimeUtils:
    """时间相关工具函数集合"""
    
    @staticmethod
    def timestamp() -> int:
        """获取当前 UTC 时间戳（秒）"""
        return int(datetime.now(timezone.utc).timestamp())

    @staticmethod
    def timestamp_ms() -> int:
        """获取当前 UTC 时间戳（毫秒）"""
        return int(datetime.now(timezone.utc).timestamp() * 1000)
    
    @staticmethod
    def now_iso() -> str:
        """获取当前 UTC 时间的 ISO 8601 格式字符串"""
        return datetime.now(timezone.utc).isoformat(timespec="seconds")
    
    @staticmethod
    def fromtimestamp(timestamp: int, strftime: str = "%Y-%m-%d %H:%M:%S") -> Optional[str]:
        """将时间戳转换为指定格式的 UTC 时间字符串"""
        if timestamp is None:
            return None
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).strftime(strftime)

    @staticmethod
    def get_reset_date(current_timestamp: int, days: int = 0) -> int:
        """获取 Recent 服务重置日期（返回 YYYYMMDD 格式的整数）"""
        reset_timestamp = current_timestamp + EnvConfig.TIMEZONE * 3600 - SERVER_RESET_OFFSET * 3600 - days * 86400
        return int(datetime.fromtimestamp(reset_timestamp, timezone.utc).strftime("%Y%m%d"))

    @staticmethod
    def get_reset_date_list(current_timestamp: int, start_date: int) -> List[int]:
        """获取从今日起至指定日期的 Recent 服务重置日期列表（最多 1000 天）"""
        result = []
        # 设置循环最大次数，防止死循环
        for _ in range(1000):
            reset_timestamp = current_timestamp + EnvConfig.TIMEZONE * 3600 - SERVER_RESET_OFFSET * 3600
            strftime = int(datetime.fromtimestamp(reset_timestamp, timezone.utc).strftime("%Y%m%d"))
            result.append(strftime)
            if strftime == start_date:
                break
            current_timestamp -= 86400
        return result

    def async_timing(func):
        """
        测试异步函数运行时间的装饰器
        """
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            result = await func(*args, **kwargs)
            end = time.time()
            api_logger.info(f"[Timing] {func.__name__} Cost: {end - start:.6f} s")
            return result
        return async_wrapper

    def sync_timing(func):
        """
        测试同步函数运行时间的装饰器
        """
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            result = func(*args, **kwargs)
            end = time.time()
            api_logger.info(f"[Timing] {func.__name__} Cost: {end - start:.6f} s")
            return result
        return sync_wrapper

