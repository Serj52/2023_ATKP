import pika
from CONFIG import Config as cfg
import json
import time
from b_lib import log
import logging
import logging.config



class Rabbit:
    def __int__(self):
        self.login = cfg.rabbit_login
        self.password = cfg.rabbit_pwd
        self.port = cfg.rabbit_port
        self.host = cfg.rabbit_host
        self.path = cfg.path
        self.task_id = None
        self.queue_response = None

    def connection(self, max_tries=5):
        while True:
            try:
                credentials = pika.PlainCredentials(cfg.rabbit_login, cfg.rabbit_pwd)
                parameters = pika.ConnectionParameters(cfg.rabbit_host, cfg.rabbit_port, cfg.path, credentials)
                connection = pika.BlockingConnection(parameters)
                return connection
            except Exception:
                if max_tries == 0:
                    logging.error('Попытки подключиться к RabbitMQ исчерпаны')
                    raise
                else:
                    logging.error('Ошибка подключения к RabbitMQ! Пробую подключиться повторно')
                    max_tries -= 1

    def send_data_queue(self, queue_response, data):
        channel = self.connection().channel()
        channel.queue_declare(queue=queue_response, durable=True)
        # Отметить сообщения как устойчивые delivery_mode=2, защищенные от потери
        channel.basic_publish(exchange='',
                              routing_key=queue_response,
                              body=data,
                              properties=pika.BasicProperties(delivery_mode=2, )
                              )
        logging.info(f'Сообщение отправлено в очередь {queue_response}')
        #сохранение отправленного json в папке с запросом
        channel.close()
        self.connection().close()

    def check_queue(self, queue=cfg.queue_request):
        """
        Получить сообщения из очереди
        """
        tasks = []
        channel = self.connection().channel()
        while True:
            method_frame, header_frame, body = channel.basic_get(queue)
            if method_frame:
                channel.basic_ack(method_frame.delivery_tag)
                data = json.loads(body)
                tasks.append(data)
            else:
                return tasks

    def producer_queue(self, queue_name, data_path):
        channel = self.connection().channel()
        # Создается очередь.устойчивая очередь durable=True к падению сервера с rabbit mq. Сообщения останутся в очереди после падения сервера
        channel.queue_declare(queue=queue_name, durable=True)

        with open(data_path, mode='rb') as file:
            # messageBody = json.dumps('Hello world', sort_keys=True, indent=4)
            messageBody = file.read()
            # Отметить сообщения как устойчивые delivery_mode=2, защищенные от потери
            channel.basic_publish(exchange='',
                                  routing_key=queue_name,
                                  body=messageBody,
                                  properties=pika.BasicProperties(delivery_mode=2, )
                                  )

        print("Sent")
        time.sleep(2)
        self.connection().close()

    def consumer_queue(self, queue_name):
        channel = self.connection().channel()
        # Создается очередь.устойчивая очередь к падению сервера с rabbit mq
        channel.queue_declare(queue=queue_name, durable=True)

        def callback(ch, method, properties, body):
            time.sleep(3)
            doc = json.loads(body)
            print(" [x] Received %r" % doc)
            # не давать нов задачу пока не сделает имеющуюся
            # ch.basic_qos(prefetch_count=1)
            # Подтверждение получения сообщения. Без него сообщения будут выводиться заново после падения обработчика.
            ch.basic_ack(delivery_tag=method.delivery_tag)

        # on_message_callback=callback даже если вы убьете рабочего с помощью CTRL+C во время обработки сообщения, ничего не будет потеряно.
        # Вскоре после смерти работника все неподтвержденные сообщения будут доставлены повторно.
        channel.basic_consume(queue=queue_name, on_message_callback=callback)
        print(' [*] Waiting for messages. To exit press CTRL+C')
        channel.start_consuming()
