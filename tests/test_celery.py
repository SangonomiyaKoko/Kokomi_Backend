from celery import Celery
import os
from dotenv import load_dotenv

load_dotenv()

RABBITMQ_HOST = os.getenv("RABBITMQ_HOST")
RABBITMQ_USERNAME = os.getenv("RABBITMQ_USERNAME")
RABBITMQ_PASSWORD = os.getenv("RABBITMQ_PASSWORD")

celery_app = Celery(
    'producer',
    broker=f"pyamqp://{RABBITMQ_USERNAME}:{RABBITMQ_PASSWORD}@{RABBITMQ_HOST}//",
    broker_connection_retry_on_startup=True
)

celery_app.send_task(
    name='user_refresh', 
    args=[{'region_id': 1, 'account_id': 2023619513}], 
    queue='refresh_queue'
)