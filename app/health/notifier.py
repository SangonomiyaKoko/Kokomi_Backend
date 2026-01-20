from app.core import api_logger

class EmailNotifier:
    def send(title: str, message: str):
        try:
            # TODO: 异常消息发送
            raise NotImplementedError
        except:
            api_logger.error('Emain failed to send!')