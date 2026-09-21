from celery import Celery
from shard import CommonConfig

from .context import RunContext
from .refresher import UserRefresher
from .settings import ENV_FILE, RABBITMQ_CONFIG


# 资源上下文
print(f"Env config loaded: {ENV_FILE}")
run_ctx = RunContext()

# 创建 Celery 应用
_broker = (
    f"pyamqp://{RABBITMQ_CONFIG['user']}"
    f":{RABBITMQ_CONFIG['password']}"
    f"@{RABBITMQ_CONFIG['host']}/"
)
celery_app = Celery(
    "tasks",
    broker=_broker,  # RabbitMQ 连接地址
    backend="rpc://",  # 使用 RabbitMQ 作为结果存储
    broker_connection_retry_on_startup=True
)

# 配置 Celery
celery_app.conf.update(
    task_routes={
        CommonConfig.REFRESH_TASK_NAME: {
            'queue': CommonConfig.REFRESH_QUEUE_NAME
        }
    }
)

@celery_app.task(name=CommonConfig.REFRESH_TASK_NAME)
def task_update_user_data(payload: dict):
    """更新用户数据库的数据"""
    
    account_id = payload.get('uid')
    # 效验参数是否合法
    if not isinstance(account_id, int):
        return f'InvalidParams: {payload}'

    # 主流程
    result = UserRefresher.refresh(
        run_ctx=run_ctx, 
        account_id=account_id
    )

    return f'{account_id} - {result}'