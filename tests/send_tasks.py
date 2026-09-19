import os
import logging
import argparse
from pathlib import Path
from celery import Celery
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ROOT_DIR = Path(os.getcwd())

if (ROOT_DIR / 'env.dev').exists():
    logger.info('Loading environment file: env.dev')
    load_dotenv('env.dev')
elif (ROOT_DIR / 'env.prod').exists():
    logger.info('Loading environment file: env.prod')
    load_dotenv('env.prod')
else:
    raise FileNotFoundError('No environment file found')

RABBITMQ_CONFIG = {
    "host": os.getenv("RABBITMQ_HOST"),
    "user": os.getenv("RABBITMQ_DEFAULT_USER"),
    "password": os.getenv("RABBITMQ_DEFAULT_PASS")
}

def main(task_id: int):
    _broker = (
        f"pyamqp://{RABBITMQ_CONFIG['user']}"
        f":{RABBITMQ_CONFIG['password']}"
        f"@{RABBITMQ_CONFIG['host']}/"
    )
    celery_app = Celery(
        'producer',
        broker=_broker,
        broker_connection_retry_on_startup=True
    )
    task_tag = 'user_refresh'
    args = [{'uid': task_id}]
    celery_app.send_task(
        name=task_tag,
        args=args,
        queue='refresh_queue'
    )
    logger.info(f'Success: {task_tag} -> {task_id}')
    celery_app.close()


if __name__ == '__main__':
    """用于在本地开发环境中，手动发送 Celery 任务

    使用示例：
    python tests/send_tasks.py -i 7000005269
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        '-i', '--id', 
        required=True, 
        type=int, 
        help='Task UID'
    )
    args = parser.parse_args()
    uid = args.id

    try:
        main(
            task_id=uid
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user")