from app.middlewares import RedisClient
from app.utils import TimeUtils


class ServiceMetrics:
    async def requests_incr(key: str, date: str):
        await RedisClient.incr(f"metrics:{key}:{date}")

    async def http_incrby(region: str, date: str, amount: int):
        await RedisClient.incrby(f"metrics:http:{date}:{region}_total", amount)

    async def http_error_incrby(region: str, date: str, amount: int):
        await RedisClient.incrby(f"metrics:http:{date}:{region}_error", amount)