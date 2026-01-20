import pika
from celery import Celery
from celery.app.base import logger

from .settings import (
    RABBITMQ_HOST, RABBITMQ_PASSWORD, RABBITMQ_USERNAME
)


# params = pika.URLParameters(
#     "amqp://{RABBITMQ_USERNAME}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}/"
# )
# connection = pika.BlockingConnection(params)
# channel = connection.channel()
# logger.info("RabbitMQ connected OK")
# connection.close()

# 创建 Celery 应用
celery_app = Celery(
    "tasks",
    broker=f"pyamqp://{RABBITMQ_USERNAME}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}/",  # RabbitMQ 连接地址
    backend="rpc://",  # 使用 RabbitMQ 作为结果存储
    include=['tasks.tasks'],
    broker_connection_retry_on_startup = True
)

# 配置 Celery
celery_app.conf.update(
    task_routes={
        "tasks.add.refresh": {"queue": "refresh_queue"}
    }
)

celery_app.conf.result_expires = 86400  # 设置任务结果过期时间为 24 小时（86400 秒）