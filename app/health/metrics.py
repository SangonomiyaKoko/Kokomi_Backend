import os
import csv
from collections import defaultdict
from datetime import datetime, timedelta

from app.core import API_LOG_PATH, ERROR_LOG_PATH
from app.middlewares import RedisClient


class ServiceMetrics:
    async def requests_incr(key: str, date: str):
        await RedisClient.incr(f"metrics:{key}:{date}")

    async def http_incrby(region: str, date: str, amount: int):
        await RedisClient.incrby(f"metrics:http:{date}:{region}_total", amount)

    async def http_error_incrby(region: str, date: str, amount: int):
        await RedisClient.incrby(f"metrics:http:{date}:{region}_error", amount)
    
    @staticmethod
    def collect_today_hourly_metrics():
        # UTC+8
        now = datetime.now()
        today = now.date()
        total_count = 0
        total_elapsed_ms = 0
        # 初始化桶
        buckets = defaultdict(int)
        # buckets = defaultdict(lambda: {"value1": 0, "value2": 0})
        file = os.path.join(API_LOG_PATH, f"{today.isoformat()}.csv")
        if os.path.exists(file):
            with open(file, newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    try:
                        ts = datetime.fromisoformat(row["timestamp"])
                        es = int(row["elapsed_ms"])
                    except Exception:
                        continue
                    if ts.date() != today:
                        continue
                    hour_key = ts.strftime("%H:00")
                    buckets[hour_key] += 1
                    total_count += 1
                    total_elapsed_ms += es
        keys = []
        values = []
        current_hour = now.replace(minute=0, second=0, microsecond=0)
        for hour in range(24):
            hour_time = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            key = hour_time.strftime("%H:00")
            keys.append(key)
            if hour_time > current_hour:
                values.append(None)
            else:
                values.append(buckets.get(key, 0))
        error_count = 0
        file = os.path.join(ERROR_LOG_PATH, f"{today.isoformat()}.txt")
        if os.path.exists(file):
            with open(file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith('>Platform:'):
                        error_count += 1
        return {
            "summary":{
                "total_requests": total_count,
                "total_errors": error_count,
                "elapsed_ms": 0 if total_count == 0 else int(total_elapsed_ms/total_count)
            },
            "hourly": {
                "keys": keys,
                "series":[
                        {
                        "name": "resquest",
                        "type": "bar",
                        "data": values
                    }
                ]
            }
        }
    
    @staticmethod
    async def collect_api_metrics():
        now = datetime.now()
        keys = []
        for i in range(30, 0, -1):
            day = now - timedelta(days=i)
            keys.append(day.date().isoformat())
        values = await RedisClient.get_by_pipe("metrics:api:key", keys)
        if values['code'] != 1000:
            values = [None * 30]
        else:
            values = values['data']
        return {
            "keys": keys,
            "series":[
                    {
                    "name": "resquest",
                    "type": "bar",
                    "data": values
                }
            ]
        }
    
    @staticmethod
    async def collect_celery_metrics():
        now = datetime.now()
        keys = []
        for i in range(30, 0, -1):
            day = now - timedelta(days=i)
            keys.append(day.date().isoformat())
        values = await RedisClient.get_by_pipe("metrics:celery:key", keys)
        if values['code'] != 1000:
            values = [None * 30]
        else:
            values = values['data']
        return {
            "keys": keys,
            "series":[
                    {
                    "name": "resquest",
                    "type": "bar",
                    "data": values
                }
            ]
        }
    
    @staticmethod
    async def collect_http_metrics():
        now = datetime.now()
        today_count = [0,0]
        dates = []
        counts = [[],[],[],[],[],[],[],[],[],[]]
        for i in range(14, -1, -1):
            if i == 0:
                keys = ['asia_total','eu_total','na_total','ru_total','cn_total','asia_error','eu_error','na_error','ru_error','cn_error']
                values = await RedisClient.get_by_pipe(f"metrics:http:{day.date().isoformat()}:key", keys)
                if values['code'] == 1000:
                    values = values['data']
                    today_count[0] = values[0] + values[1] + values[2] + values[3] + values[4]
                    today_count[1] = values[5] + values[6] + values[7] + values[8] + values[9]
            else:
                day = now - timedelta(days=i)
                dates.append(day.date().isoformat())
                keys = ['asia_total','eu_total','na_total','ru_total','cn_total','asia_error','eu_error','na_error','ru_error','cn_error']
                values = await RedisClient.get_by_pipe(f"metrics:http:{day.date().isoformat()}:key", keys)
                if values['code'] != 1000:
                    values = [None * 10]
                else:
                    values = values['data']
                j = 0
                for count in values:
                    if count != None:
                        if j > 4:
                            counts[j].append(0 if values[j-5] == 0 else round(count/values[j-5],1))
                        else:
                            counts[j].append(count)
                    else:
                        counts[j].append(None)
                    j += 1
        return today_count, {
            "keys": dates,
            "series":[
                {"name": "asia","type": "line","data": counts[0]},
                {"name": "eu","type": "line","data": counts[1]},
                {"name": "na","type": "line","data": counts[2]},
                {"name": "ru","type": "line","data": counts[3]},
                {"name": "cn","type": "line","data": counts[4]},
            ]
        }, {
            "keys": dates,
            "series":[
                {"name": "asia","type": "line","data": counts[5]},
                {"name": "eu","type": "line","data": counts[6]},
                {"name": "na","type": "line","data": counts[7]},
                {"name": "ru","type": "line","data": counts[8]},
                {"name": "cn","type": "line","data": counts[9]},
            ]
        }