from .main import celery_app
from .scripts import refresh_user


@celery_app.task(name="user_refresh")
def task_update_user_data(user_id: dict):
    """更新用户数据库的数据"""
    result = refresh_user(user_id)
    return result

# @celery_app.task(name="data_refresh")
# def task_sum_recent(data: dict):
#     """更新近期数据"""
#     result = sum_recent(data)
#     return result

