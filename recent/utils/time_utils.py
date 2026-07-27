from datetime import datetime, timezone

from settings import (
    DATE_FMT,
    TIMEZOEN, 
    SERVER_RESET_OFFSET
)

class TimeUtils:
    def get_formatted_date() -> str:
        """获取当前日期格式化字符串，用于日志输出"""
        return datetime.now().strftime(DATE_FMT)

    def get_current_timestamp() -> int:
        """获取当前 UTC 时间的 int 类型时间戳（秒）"""
        return int(datetime.now(timezone.utc).timestamp())

    def get_current_iso_time() -> str:
        """获取当前 UTC 时间的 ISO 格式字符串"""
        return datetime.now(timezone.utc).isoformat(timespec='seconds')

    def get_reset_date(current_timestamp: int) -> int:
        """获取服务器重置日期（基于当地凌晨5点更新）"""
        reset_timestamp = current_timestamp + TIMEZOEN * 3600 - SERVER_RESET_OFFSET * 3600
        strftime = datetime.fromtimestamp(reset_timestamp, timezone.utc).strftime("%Y%m%d")
        return int(strftime)

    def get_reset_date_list(current_timestamp: int, start_date: int) -> list[int]:
        """获取服务器重置日期列表，返回从当前日期直至指定的日期（从新到旧）"""
        result = []
        for _ in range(1000):
            reset_timestamp = current_timestamp + TIMEZOEN * 3600 - SERVER_RESET_OFFSET * 3600
            strftime = int(datetime.fromtimestamp(reset_timestamp, timezone.utc).strftime("%Y%m%d"))
            result.append(strftime)
            if strftime == start_date:
                break
            current_timestamp -= 86400
        # 确保日期严格递减（从新到旧）
        for i in range(len(result) - 1):
            if result[i] <= result[i + 1]:
                raise RuntimeError("Date list not in strictly decreasing order")
        return result   