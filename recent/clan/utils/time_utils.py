from datetime import datetime, timezone

from settings import DATE_FMT


def get_formatted_date() -> str:
    """获取当前日期格式化字符串，用于日志输出"""
    return datetime.now().strftime(DATE_FMT)

def get_current_timestamp() -> int:
    """获取当前 UTC 时间的 int 类型时间戳（秒）"""
    return int(datetime.now(timezone.utc).timestamp())

def get_current_iso_time() -> str:
    """获取当前 UTC 时间的 ISO 格式字符串"""
    return datetime.now(timezone.utc).isoformat(timespec='seconds')

def formtime_to_timestamp(formtime: str) -> int:
    """将 ISO 格式时间字符串转换为 Unix 时间戳"""
    return int(datetime.fromisoformat(formtime).timestamp())
