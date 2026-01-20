import httpx
from httpx import Auth

from app.core import api_logger, EnvConfig
from app.middlewares import RedisClient

async def server_check():
    for server_name in ['SchedulerUser', 'SchedulerClan']:
        redis_key = f"status:{server_name}"
        result = await RedisClient.exists(redis_key)
        if result['data'] != 1:
            # 服务离线
            api_logger.warning(f"{server_name} Server offline.")
        else:
            # 服务正常
            api_logger.info(f"{server_name} Server running.")

async def rabbitmq_check():
    config = EnvConfig.get_config()
    url = f'http://{config.RABBITMQ_HOST}:15672/api'
    client = httpx.Client(
        base_url=url,
        auth=(config.RABBITMQ_USERNAME, config.RABBITMQ_PASSWORD),
        timeout=2
    )
    resp = client.get('/queues/%2F/refresh_queue')
    if resp.status_code != 200:
        api_logger.warning("Failed to retrieve RabbitMQ API data.")
    result = resp.json()
    messages = result.get('messages', 0)
    if messages <= 1000:
        api_logger.info(f"Current RabbitMQ message backlog: {messages}.")
    else:
        api_logger.warning(f"Current RabbitMQ message backlog: {messages}.")