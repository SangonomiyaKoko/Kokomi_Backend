import pika

params = pika.URLParameters(
    "amqp://root:qazwsxedc0258@127.0.0.1/"
)

connection = pika.BlockingConnection(params)
channel = connection.channel()
print("RabbitMQ connected OK")
connection.close()