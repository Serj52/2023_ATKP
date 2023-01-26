from datetime import datetime
from CONFIG import Config as cfg
import Lib.RABBIT
import logging
import json
import traceback
import smtplib
from Lib.DATABASE import DateBase
import Lib.b_outlook
import uuid


def exception_decorator(method):
    def wraper(self, *args):
        try:
           return method(self, *args)
        except TemplateError as err:
            err.exception_handler(queue=self.queue, tasks=self.task, type_error='Не найден шаблон', to_rabbit='on')
        except NotFoundEmployee as err:
            err.exception_handler(queue=self.queue, tasks=self.task, type_error='Не найдено ФИО', to_rabbit='on')
        except NotFoundOrganization as err:
            err.exception_handler(queue=self.queue, tasks=self.task, type_error='Не найдена Организация',
                                  to_rabbit='on')
        except NotFoundDocument as err:
            err.exception_handler(queue=self.queue, tasks=self.task, type_error='Не найден документ')

        except SendError as err:
            err.exception_handler(queue=self.queue, tasks=self.task, type_error='Ошибка при отправке почты',
                                  to_rabbit='on', to_mail='on')

        except ReceivingError as err:
            err.exception_handler(type_error='Ошибка при мониторинге почты', to_mail='on', stop_robot='on')

        except SaveProjectError as err:
            err.exception_handler(queue=self.queue, tasks=self.task, type_error='Ошибка при сохрании данных о проекте',
                                  to_rabbit='on')

        except AuthorizationError as err:
            if self.__class__.__name__ == 'EosdoReg':
                err.exception_handler(queue=self.queue, tasks=self.tasks, type_error='Ошибка авторизации в ЕОСДО',
                                      to_rabbit='on', to_mail='on')
            else:
                err.exception_handler(queue=self.queue, tasks=self.tasks, type_error='Ошибка при открытии ЕОСДО',
                                      to_mail='on')

        except OpenEOSDOError as err:
            if self.__class__.__name__ == 'EosdoReg':
                err.exception_handler(queue=self.queue, tasks=self.tasks, type_error='Ошибка при открытии ЕОСДО',
                                      to_rabbit='on', to_mail='on')
            else:
                err.exception_handler(queue=self.queue, tasks=self.tasks, type_error='Ошибка при открытии ЕОСДО',
                                      to_mail='on')

        except json.JSONDecodeError as err:
            logging.error(err)
            if method.__name__ == 'check_queue':
                logging.error(f'Ошибка кодировки в запросе {err}. Ожидал json.')
                ExceptionHandler().exception_handler(queue=cfg.queue_error,
                                                     text_error='Проверьте кодировку. Ожидал json',
                                                     type_error='bad_request', to_rabbit='on')
    return wraper



class ExceptionHandler:

    def exception_handler(self, queue=None, text_error='', tasks=None, type_error=None,
                          to_rabbit='off', to_mail='off', stop_robot='', rec_to_db=True):
        """
        Обработка исключений
        :param queue: очередь для отправки сообщений
        :param text_error: текст сообщения об исклчюении
        :param tasks: id запроса
        :param parameters_request: параметры запроса
        :param type_error: тип ошибки
        :param not_found_files: не найденные файлы в архиве
        :param to_rabbit: отправка сообщения через rabbit
        :param to_mail: отправка сообщения через BusinessOutlook
        :param stop_robot: остановка робота
        """
        try:
            trace = traceback.format_exc()
            logging.error(f'\n\n{trace}')

            # запись в БД ошибки
            if rec_to_db:
                if isinstance(tasks, list):
                    for task in tasks:
                        DateBase().add_error(task, type_error)
                else:
                    DateBase().add_error(tasks, type_error)

            if to_rabbit == 'on':
                if isinstance(tasks, list):
                    for task in tasks:
                        body_task = DateBase().get_one(task, 'ЗАПРОС', 'dict')
                        queue = body_task['header']['replayRoutingKey']
                        json_data = self.create_error_json(type_error=type_error, task_id=task)
                        Lib.RABBIT.Rabbit().send_data_queue(queue_response=queue, data=json_data)
                else:
                    json_data = self.create_error_json(type_error=type_error, task_id=tasks)
                    Lib.RABBIT.Rabbit().send_data_queue(queue_response=queue, data=json_data)

            if to_mail == 'on':
                text = self.get_message(type_error=type_error, text_error=text_error, task_id=tasks)
                subject = cfg.robot_name
                body = 'Добрый день! \n ' \
                           f'{text}\n' \
                           f'{trace}'
                try:
                    Lib.b_outlook.BusinessOutlook.send_mail(cfg.support_email, subject, body)
                except Exception as err:
                    logging.error(f'Ошибка отправки уведомления через Outlook: {err}. Пробую через SMTP.')
                    self.send_smtp(from_mail=cfg.robot_mail,
                                   to=cfg.support_email,
                                   subject=subject,
                                   text=body)
            if stop_robot:
                # завершаем работу робота
                logging.info('РОБОТ ОСТАНОВЛЕН')
                exit(-1)
        except Exception as err:
            logging.error(f'Ошибка внутри блока обработки ошибок: {err}')
            subject = cfg.robot_name
            trace = traceback.format_exc()
            body = 'Добрый день! \n ' \
                   f'{err}\n' \
                   f'{trace}'
            try:
                Lib.b_outlook.BusinessOutlook().send_mail(cfg.support_email, subject, body)
            except Exception as err:
                logging.error(err)
                self.send_smtp(from_mail=cfg.robot_mail,
                               to=cfg.support_email,
                               subject=subject,
                               text=body)

    @staticmethod
    def send_smtp(from_mail, to, subject, text):
        logging.info('Отправляю письмо')
        try:
            conn = smtplib.SMTP(cfg.server_mail, 25)
            text = "From:{0}\nTo:{1}\nSubject:{2}\n\n{3}".format(from_mail, to, subject, text).encode("utf-8")
            conn.sendmail(from_mail, to, text)
        except Exception as err:
            logging.error(f'Письмо не отправлено:\n{err}\n'
                          f'Ошибка при отправке письма через SMTP:\n\n{traceback.format_exc()}')

    @staticmethod
    def create_error_json(type_error, task_id):
        """
        Создание файла json о возникшем исключении
        :param type_error: тип исключения
        :param task_id: id запроса
        :param text_error: текст сообщения об исключении
        :return: json_path
        """
        with open(cfg.response_error) as out_file:
            logging.info(f'Записываю в json ошибку {type_error}')
            data = json.load(out_file)
        data["header"]["id"] = id = str(uuid.uuid4())
        data["header"]["sourceId"] = task_id
        data["header"]["date"] = str(datetime.now())
        data["ErrorText"] = type_error
        data_json = json.dumps(data, indent=2, ensure_ascii=False)
        DateBase().response_db(id, data, type_error, task_id)
        return data_json

    @staticmethod
    def get_message(type_error, *, text_error=None, task_id=''):
        """
        Формируем сообщение об ошибки
        :param task_id: id запроса
        :param type_error: тип исключения
        :param text_error: текст сообщения об исключении
        :return: текст сообщения об исключении
        """
        text = ''
        if type_error == 'processing_file_error':
            text = f'Ошибка обработки файла. Запрос {task_id} завершился неудачно'
        elif type_error == 'download_error':
            text = f'Ошибка при загрузке данных c сайта. Запрос {task_id} завершился неудачно'
        elif type_error == 'website_error':
            text = f'Нет доступа к сайту. Запрос {task_id} завершился неудачно'
        elif type_error == 'unknown_error':
            text = f'Непредвиденная ошибка при обработки запроса {task_id}.'
        elif type_error == 'connect_rabbit_error':
            text = 'Не удалось подключиться к серверу RabbitMq.'
        elif type_error == 'bad_request':
            text = f'Ошибка обработки запроса {task_id}. {text_error}'
        elif type_error == 'no_updates':
            text = f'На сайте обновлений не обнаружено.'
        elif type_error == 'not_found_element':
            text = f'Не удалось найти элемент на странице. Проверьте верстку на сайте. Запрос {task_id} завершился неудачно'
        elif type_error == 'not_found_data':
            text = f'Данные в запрашиваемом периоде не найдены. Повторите запрос. Запрос {task_id} завершился неудачно'
        elif type_error == 'exctract_error':
            text = f'Ошибка при распаковке архива'
        elif type_error == 'robot_sleep':
            text = f'Сайт не доступен. Повторную попытку робот осуществит через два часа'
        elif type_error == 'not_found_files':
            text = f'Не найдено ни одного файла в загруженом архиве.'
        return text


class WebsiteError(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class TemplateError(Exception,  ExceptionHandler):
    def __init__(self, text):
        self.txt = text

class SendError(Exception,  ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class ReceivingError(Exception,  ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class FileProcessError(Exception,  ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class NoUpdatesError(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class BadRequest(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class NotFoundElement(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text

class ExctractError(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text

class NotFoundFiles(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text

class EOSDOError(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text

class OpenEOSDOError(Exception,  ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class AuthorizationError(Exception,  ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class NotFoundDocument(Exception,  ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class NotFoundEmployee(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text


class NotFoundOrganization(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text

class SaveProjectError(Exception, ExceptionHandler):
    def __init__(self, text):
        self.txt = text