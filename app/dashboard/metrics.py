import csv
import httpx
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple

from shard import RedisKeys, ServicesName

from app.middlewares import RedisClient


class ServiceMetrics:
    async def get_today_celery_error_count(date_str: str) -> int:
        """获取今日 Celery 任务失败数量"""
        result = await RedisClient.get(f"metrics:celery:daily:error:{date_str}")
        if result['code'] == 1000 and result['data'] is not None:
            return int(result['data'])
        return 0

    def get_hourly_request_stats(today, log_dir) -> Tuple[int, Dict[str, int], int, int, Dict[str, Any]]:
        """统计过去24h的请求数据
        Returns:
            total_count: 总请求数
            buckets: 按小时分组的请求数 { "08:00": 100, ... }
            avg_elapsed_ms: 平均响应时间(ms)
            status_200_count: status_code 为 200 的请求数
            hourly_avg_elapsed: 按小时分组的平均响应时间(ms) { "08:00": 150.5, ... }，无请求的小时为 None
        """
        total_count = 0
        total_elapsed_ms = 0
        status_200_count = 0
        buckets = defaultdict(int)
        hourly_elapsed = defaultdict(int)
        hourly_count = defaultdict(int)

        file = log_dir / f"metrics/{today.isoformat()}.csv"
        if file.exists():
            with open(file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        ts = datetime.fromisoformat(row["timestamp"])
                        es = int(row["elapsed_ms"])
                        sc = int(row["status_code"])
                    except Exception:
                        continue
                    if ts.date() != today:
                        continue
                    hour_key = ts.strftime("%H:00")
                    buckets[hour_key] += 1
                    hourly_elapsed[hour_key] += es
                    hourly_count[hour_key] += 1
                    total_count += 1
                    total_elapsed_ms += es
                    if sc == 200:
                        status_200_count += 1

        avg_elapsed_ms = 0 if total_count == 0 else int(total_elapsed_ms / total_count)

        # 计算每个小时的平均响应时间，无请求的小时设为 None
        hourly_avg_elapsed = {}
        for hour in range(24):
            key = f"{hour:02d}:00"
            cnt = hourly_count.get(key, 0)
            if cnt > 0:
                hourly_avg_elapsed[key] = round(hourly_elapsed[key] / cnt, 1)
            else:
                hourly_avg_elapsed[key] = None

        return total_count, buckets, avg_elapsed_ms, status_200_count, hourly_avg_elapsed

    def build_hourly_chart_data(now, buckets: Dict[str, int]) -> Tuple[List[str], List[Any]]:
        """构建过去24h图表数据
        
        Returns:
            hourly_keys: 小时标签列表 ["00:00", "01:00", ...]
            hourly_values: 对应的请求数，未来时间为None
        """
        hourly_keys = []
        hourly_values = []
        current_hour = now.replace(minute=0, second=0, microsecond=0)

        for hour in range(24):
            hour_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            key = hour_time.strftime("%H:00")
            hourly_keys.append(key)
            if hour_time > current_hour:
                hourly_values.append(None)
            else:
                hourly_values.append(buckets.get(key, 0))
        
        return hourly_keys, hourly_values

    async def get_monthly_api_stats(now) -> Tuple[List[str], List[Any]]:
        """获取过去30d API调用统计数据
        Returns:
            monthly_keys: 日期标签列表
            monthly_values: 对应的API调用数
        """
        monthly_keys = []
        monthly_redis_keys = []

        for i in range(30, -1, -1):
            day = now - timedelta(days=i)
            monthly_keys.append(day.date().isoformat())
            monthly_redis_keys.append(f"metrics:api:daily:{day.date().isoformat()}")

        values = await RedisClient.get_by_pipe(monthly_redis_keys)
        if values['code'] != 1000:
            monthly_values = [None] * 31
        else:
            monthly_values = values['data']

        return monthly_keys, monthly_values

    async def get_monthly_http_stats(now) -> Tuple[List[str], List[Any], List[Any]]:
        """获取过去30d HTTP请求总量及错误量

        Returns:
            monthly_keys: 日期标签列表
            total_values: 每日 HTTP 请求总量
            error_values: 每日 HTTP 错误量
        """
        monthly_keys = []
        total_keys = []
        error_keys = []

        for i in range(30, -1, -1):
            day = now - timedelta(days=i)
            date_str = day.date().isoformat()
            monthly_keys.append(date_str)
            total_keys.append(f"metrics:http:daily:total:{date_str}")
            error_keys.append(f"metrics:http:daily:error:{date_str}")

        all_keys = total_keys + error_keys
        values = await RedisClient.get_by_pipe(all_keys)
        if values['code'] != 1000:
            total_values = [0] * 31
            error_values = [0] * 31
        else:
            mid = len(total_keys)
            total_values = values['data'][:mid]
            error_values = values['data'][mid:]

        return monthly_keys, total_values, error_values

    async def get_monthly_celery_stats(now) -> Tuple[List[str], List[Any]]:
        """获取过去30d Celery任务消费统计数据
        Returns:
            celery_keys: 日期标签列表
            celery_values: 对应的任务数
        """
        celery_keys = []
        celery_redis_keys = []
        
        for i in range(30, -1, -1):
            day = now - timedelta(days=i)
            celery_keys.append(day.date().isoformat())
            celery_redis_keys.append(f"metrics:celery:daily:total:{day.date().isoformat()}")
        
        values = await RedisClient.get_by_pipe(celery_redis_keys)
        if values['code'] != 1000:
            celery_values = [None] * 31
        else:
            celery_values = values['data']
        
        return celery_keys, celery_values

    async def get_monthly_celery_error_stats(now) -> Tuple[List[str], List[Any]]:
        """获取过去30d Celery失败任务统计数据
        Returns:
            error_keys: 日期标签列表
            error_values: 对应的失败任务数
        """
        error_keys = []
        error_redis_keys = []

        for i in range(30, -1, -1):
            day = now - timedelta(days=i)
            error_keys.append(day.date().isoformat())
            error_redis_keys.append(f"metrics:celery:daily:error:{day.date().isoformat()}")

        values = await RedisClient.get_by_pipe(error_redis_keys)
        if values['code'] != 1000:
            error_values = [0] * 31
        else:
            error_values = values['data']

        return error_keys, error_values

    def get_hourly_error_stats(today, log_dir) -> Tuple[int, Dict[str, int]]:
        """统计今日错误日志数及每小时分布

        Returns:
            error_count: 总错误数
            buckets: 按小时分组的错误数 {"08:00": 5, ...}
        """
        error_count = 0
        buckets = defaultdict(int)
        file = log_dir / f"error/{today.isoformat()}.log"

        if file.exists():
            with open(file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    error_count += 1
                    try:
                        hour_key = f"{line[:2]}:00"
                        buckets[hour_key] += 1
                    except Exception:
                        pass

        return error_count, buckets

    def get_celery_queue_stats(config) -> Dict[str, Any]:
        """获取 Celery 队列（refresh_queue）的统计数据

        Returns:
            dict 包含 messages, consumers, consumer_utilisation,
                 publish_total, ack_total, state 等字段
        """
        url = f'http://{config.RABBITMQ.host}:15672/api'
        client = httpx.Client(
            base_url=url,
            auth=(config.RABBITMQ.username, config.RABBITMQ.password),
            timeout=2,
            trust_env=False
        )

        try:
            resp = client.get('/queues/%2F/refresh_queue')
            if resp.status_code == 200:
                data = resp.json()
                stats = data.get('message_stats', {})
                return {
                    'pending': data.get('messages', 0),
                    'ready': data.get('messages_ready', 0),
                    'unacknowledged': data.get('messages_unacknowledged', 0),
                    'consumers': data.get('consumers', 0),
                    'utilisation': data.get('consumer_utilisation', 0),
                    'published': stats.get('publish', 0),
                    'consumed': stats.get('ack', 0),
                    'state': data.get('state', 'unknown'),
                    'memory': data.get('memory', 0),
                    'message_bytes': data.get('message_bytes', 0),
                    'reductions': data.get('reductions', 0),
                }
        except Exception:
            pass
        finally:
            client.close()

        return {}

    async def get_services_status() -> Tuple[int, int]:
        """获取服务状态
        Returns:
            active_count: 活跃服务数
            total_count: 总服务数
        """
        active_count = 0
        services = ServicesName.to_list()
        for service in services:
            key = RedisKeys.services(service)
            exists = await RedisClient.exists(key)
            if exists['code'] == 1000 and exists['data']:
                active_count += 1
        return active_count, len(services)
    
