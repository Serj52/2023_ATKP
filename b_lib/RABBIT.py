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

    #
    # def new_validator(self, tasks):
    #     valid_tasks = []
    #     for task in tasks:
    #         self.task_id = None
    #         self.queue_response = None
    #         try:
    #             self.queue_response = task['header']['replayRoutingKey']
    #             self.task_id = task['header']["requestID"]
    #             validate(task, schema)
    #             logging.info(f'Запрос {self.task_id} валиден.')
    #             valid_tasks.append(task)
    #         except jsonschema.exceptions.ValidationError as error:
    #             logging.error(error)
    #             EXCEPTION_HANDLER.ExceptionHandler().exception_handler(queue=self.queue_response, text_error=error,
    #                                                                    tasks=self.task_id, type_error='bad_request',
    #                                                                    to_rabbit='on', to_mail='on', rec_to_db=False)
    #             logging.info(f'Запрос {self.task_id} не валиден. Задание не принято в обработку')
    #     return valid_tasks
    #
    #
    # def validator(self, tasks):
    #     valid_tasks = []
    #     for index, task in enumerate(tasks):
    #         self.task_id = None
    #         self.queue_response = None
    #         errors = ''
    #         try:
    #             if task['header']['replayRoutingKey'] == '':
    #                 errors = 'Поле replayRoutingKey в запросе пустое. '
    #             else:
    #                 self.queue_response = task['header']['replayRoutingKey']
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = f'{errors} Проверьте наличие поля replayRoutingKey в запросе. '
    #
    #         try:
    #             if task['header']["requestID"] == '':
    #                 errors = f'{errors} Поле requestID в запросе пустое. '
    #             else:
    #                 self.task_id = task['header']["requestID"]
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля requestID в запросе. '
    #
    #         try:
    #             if task['body']["type_request"] == '':
    #                 errors = f'{errors} Поле type_request в запросе пустое. '
    #             else:
    #                 if task['body']["type_request"] != 'дозапрос' and task['body']["type_request"] != 'запрос':
    #                     errors = f'{errors} Поле type_request дожно быть "дозапрос" или "запрос". '
    #                 else:
    #                     try:
    #                         if task['body']["type_request"] == 'дозапрос':
    #                             if task['body']["date_related_document"] == '' or task['body']['related_document'] == '':
    #                                 errors = f'{errors} Поле date_related_document или related_document в запросе пустое. '
    #                     except KeyError as err:
    #                         logging.error(err)
    #                         errors = 'Проверьте наличие поля date_related_document в запросе. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля requestID в запросе. '
    #
    #         try:
    #             if task['header']['subject'] == '':
    #                 errors = f'{errors} Поле subject в запросе пустое. '
    #             else:
    #                 if task['header']['subject'] != 'EOSDO':
    #                     errors = f"{errors}Несоотвествующий тип запроса. Получили {task['header']['subject']} ожидалось EOSDO. "
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля subject в запросе. '
    #
    #         try:
    #             if task['body']['related_document'] == '' or task['body']['related_document'] != '':
    #                 pass
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля related_document в запросе. '
    #
    #         try:
    #             if task['body']["organization"] == '':
    #                 errors = f'{errors} Поле organization в запросе пустое. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля organization в запросе. '
    #
    #         try:
    #             if task['body']["files"] == []:
    #                 errors = f'{errors} Поле files в запросе пустое. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля files в запросе. '
    #
    #         try:
    #             if task['body']["template"] == '':
    #                 errors = f'{errors} Поле template в запросе пустое. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля template в запросе. '
    #
    #         try:
    #             if task['body']["reseivers_list"] == {}:
    #                 errors = f'{errors} Поле reseivers_list в запросе пустое. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля reseivers_list в запросе. '
    #
    #         try:
    #             if task['body']["initiator"] == "":
    #                 errors = f'{errors} Поле initiator в запросе пустое. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля initiator в запросе. '
    #
    #         try:
    #             if task['body']["purchase_item"] == "":
    #                 errors = f'{errors} Поле purchase_item в запросе пустое. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля purchase_item в запросе. '
    #
    #         try:
    #             if task['body']["mail"] == "":
    #                 errors = f'{errors} Поле mail в запросе пустое. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля mail в запросе. '
    #
    #         try:
    #             if task['body']["staff_position"] == {}:
    #                 errors = f'{errors} Поле staff_position в запросе пустое. '
    #         except KeyError as err:
    #             logging.error(err)
    #             errors = 'Проверьте наличие поля staff_position в запросе. '
    #
    #         if errors:
    #             logging.error(errors)
    #             queue = self.queue_response
    #             if self.queue_response is None:
    #                 queue = cfg.queue_error
    #             EXCEPTION_HANDLER.ExceptionHandler.exception_handler(queue=queue, text_error=errors,
    #                                                                    tasks=self.task_id, type_error='bad_request',
    #                                                                    to_rabbit='on', to_mail='on')
    #             logging.info(f'Запрос {self.task_id} не валиден. Задание не принято в обработку')
    #         else:
    #             logging.info(f'Запрос {self.task_id} валиден. {errors}')
    #             valid_tasks.append(task)
    #     return valid_tasks


if __name__ == '__main__':
    log.set_2(cfg)
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
    })

    logging.info('\n\n=== Start ===\n\n')
    logging.info(f'Режим запуска: {cfg.mode}')
    rabbit = Rabbit()
    rabbit.check_queue()