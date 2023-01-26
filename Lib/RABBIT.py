import jsonschema.exceptions
import pika
from CONFIG import Config as cfg
import json
from Lib import log
import logging
import logging.config
from datetime import datetime
from jsonschema import validate, Draft7Validator
from Templates.shema_json import schema


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
        self.connection().close()

    def check_queue(self):
        """
        Получить сообщения из очереди
        """
        tasks = []
        channel = self.connection().channel()
        while True:
            method_frame, header_frame, body = channel.basic_get(queue=cfg.queue_request)
            if method_frame:
                channel.basic_ack(method_frame.delivery_tag)
                data = json.loads(body)
                tasks.append(data)
            else:
                return tasks