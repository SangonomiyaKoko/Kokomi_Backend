from app.core import api_logger
from .notifier import EmailNotifier
from .check import server_check, rabbitmq_check

class HealthManager:
    async def refresh():
        """
        定期检测各个子服务和依赖的状态，通过邮件报告异常状态
        """
        try:
            await server_check()
            await rabbitmq_check()
        except Exception as e:
            api_logger.error('Health Manager Error!')
            raise e
        
    async def get_status():
        """
        获取api及其他子服务运行中产生的数据
        """
        try:
            raise NotImplementedError
        except Exception as e:
            api_logger.error('Health Manager Error!')
            raise e