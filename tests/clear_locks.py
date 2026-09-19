import os
import redis
import logging
import argparse
from pathlib import Path
from kombu import Connection
from dotenv import load_dotenv


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(os.getcwd())

if (ROOT_DIR / 'env.dev').exists():
    load_dotenv('env.dev')
elif (ROOT_DIR / 'env.prod').exists():
    load_dotenv('env.prod')
else:
    raise FileNotFoundError('No environment file found')

REDIS_CONFIG = {
    "host": 'localhost',
    "port": int(os.getenv("REDIS_PORT", 6379)),
    "db": int(os.getenv("REDIS_DATABASE", 0))+1,
    "password": os.getenv("REDIS_PASSWORD"),
    "decode_responses": True
}

RABBITMQ_CONFIG = {
    "host": os.getenv("RABBITMQ_HOST"),
    "user": os.getenv("RABBITMQ_DEFAULT_USER"),
    "password": os.getenv("RABBITMQ_DEFAULT_PASS")
}

def purge_refresh_queue():
    """清除 refresh_queue 队列中的消息"""
    # 构建 RabbitMQ 连接 URL
    rabbitmq_url = f"amqp://{RABBITMQ_CONFIG['user']}:{RABBITMQ_CONFIG['password']}@{RABBITMQ_CONFIG['host']}:5672//"
    
    # 建立连接
    with Connection(rabbitmq_url) as conn:
        with conn.channel() as channel:
            # 清除 refresh_queue 中的所有消息
            purged_count = channel.queue_purge('refresh_queue')
            logger.info(f"Total messages purged: {purged_count}")

def release_redis_lock():
    SCAN_BATCH_SIZE = 5000

    pattern = 'refresh_lock:queue:*'
    redis_client = redis.Redis(**REDIS_CONFIG)

    cursor = 0
    deleted_count = 0

    while True:
        cursor, keys = redis_client.scan(cursor, match=pattern, count=SCAN_BATCH_SIZE)
        if keys:
            redis_client.delete(*keys)
            deleted_count += len(keys)
        if cursor == 0:
            break

    logger.info(f"Total keys deleted: {deleted_count}")
    redis_client.close()


def main(mode: str):
    if mode == 'redis':
        release_redis_lock()
    elif mode == 'mq':
        purge_refresh_queue()
    else:
        release_redis_lock()
        purge_refresh_queue()

if __name__ == '__main__':
    """删除用户刷新的分布式锁

    运行前请确保所有子服务已停止运行，避免读取到异常数据或影响服务正常运行

    使用示例：
    python tests/clear_locks.py -m all
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-m", "--mode",
        type=str,
        required=True,
        help="Mode"
    )
    args = parser.parse_args()
    mode = args.mode
    if mode not in ['all', 'redis', 'mq']:
        raise ValueError('Incorrect mode')
    
    try:
        main(mode)
    except KeyboardInterrupt:
        logger.info("Interrupted by user")