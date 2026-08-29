import json
from datetime import datetime, timezone

from settings import (
    DATA_DIR,
    DATE_FMT,
    TIMEZONE,
    SERVER_RESET_OFFSET
)

class TimeUtils:
    def get_formatted_date() -> str:
        """获取当前日期格式化字符串，用于日志输出"""
        return datetime.now().strftime(DATE_FMT)

    def get_current_timestamp() -> int:
        """获取当前 UTC 时间的 int 类型时间戳，单位为秒"""
        return int(datetime.now(timezone.utc).timestamp())

    def get_current_iso_time() -> str:
        """获取当前 UTC 时间的 ISO 格式字符串"""
        return datetime.now(timezone.utc).isoformat(timespec='seconds')

    def get_reset_date(current_timestamp: int) -> int:
        """获取服务器重置日期，基于当地凌晨 5 点更新"""
        reset_timestamp = (
            current_timestamp
            + TIMEZONE * 3600
            - SERVER_RESET_OFFSET * 3600
        )
        strftime = datetime.fromtimestamp(
            reset_timestamp, timezone.utc
        ).strftime("%Y%m%d")
        return int(strftime)

    def get_reset_date_list(current_timestamp: int, start_date: int) -> list[int]:
        """获取服务器重置日期列表，返回从当前日期到指定日期的日期，从新到旧排列"""
        result = []
        for _ in range(1000):   # 正常情况下不可能超过 1000 天，此处为避免死循环
            reset_timestamp = (
                current_timestamp
                + TIMEZONE * 3600
                - SERVER_RESET_OFFSET * 3600
            )
            strftime = int(
                datetime.fromtimestamp(reset_timestamp, timezone.utc)
                .strftime("%Y%m%d")
            )
            result.append(strftime)
            if strftime == start_date:
                break
            current_timestamp -= 86400

        # 确保日期严格递减，从新到旧
        for i in range(len(result) - 1):
            if result[i] <= result[i + 1]:
                raise RuntimeError("Date list not in strictly decreasing order")
        return result

    def is_cb_active() -> int | None:
        """读取 CLAN 模式赛季信息，检测当前时间是否属于更新活跃时间段"""
        now_ts = int(datetime.now(timezone.utc).timestamp())

        # 从本地文件中读取 CLAN 模式最新赛季数据
        file_path = DATA_DIR / 'json/clan_season.json'
        if not file_path.exists():
            start_timestamp = None
            finish_timestamp = None
        else:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            start_timestamp = data.get('start')
            finish_timestamp = data.get('finish')

        # 未配置 CLAN 模式活跃时间段时默认不活跃
        if not start_timestamp or not finish_timestamp:
            return None

        # 当前时间不在 CLAN 赛季时间范围内
        if not (start_timestamp <= now_ts <= finish_timestamp):
            return None

        # 转换为服务器当地时间
        local_ts = now_ts + TIMEZONE * 3600
        dt = datetime.fromtimestamp(local_ts, tz=timezone.utc)

        # 周一 / 周四 / 周五 / 周日的 01:00–05:00 为更新活跃时间段
        if dt.isoweekday() not in (1, 4, 5, 7) or not (1 <= dt.hour < 5):
            return None

        # 当前活跃时间段的开始时间：当地时间当天 01:00
        period_start = dt.replace(
            hour=1,
            minute=0,
            second=0,
            microsecond=0,
        )

        # 转回 UTC Unix timestamp
        period_start_ts = int(
            period_start.timestamp() - TIMEZONE * 3600
        )

        return period_start_ts
