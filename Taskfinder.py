
from typing import Union
from b_lib import log, DATABASE, RABBIT
import logging.config
import logging
from CONFIG import Config as cfg
from b_lib.error_handler import ErrorHandler
from b_lib import EXCEPTION_HANDLER
from eosdomon import EosdoMon
from eosdoreg import EosdoReg
from eosdoreceive import EosdoReceive
from sender import Sender
from jsonschema import validate
from Templates.shema_json import schema



class TaskFinder:
    def __init__(self):
        self.rabbit = RABBIT.Rabbit()
        self.db = DATABASE.DateBase()
        self.eosdo_reg = EosdoReg()
        self.eosdo_mon = EosdoMon()
        self.eosdo_res = EosdoReceive()
        self.sender = Sender()

    def run_process(self, obj: Union[EosdoReg, EosdoMon, EosdoReceive], tasks: list) -> None:
        tasks_organizations = self.prepare_tasks(tasks)
        for organization in tasks_organizations:
            logging.info(f'Обрабатываю задания для {organization}')
            obj.start_process(tasks_organizations[organization], organization)

    def validator(self, tasks: list) -> list:
        valid_tasks = []
        for task in tasks:
            self.task = None
            self.queue = None
            try:
                self.queue = task['header']['replayRoutingKey']
                self.task = task['header']["requestID"]
                validate(task, schema)
                logging.info(f'Запрос {self.task} валиден.')
                valid_tasks.append(task)
            except Exception as error:
                if self.queue is None:
                    self.queuee = cfg.queue_error
                logging.error(error)
                EXCEPTION_HANDLER.ExceptionHandler().exception_handler(queue=self.queue,
                                                                       tasks=self.task,
                                                                       type_error=f'Запрос не валиден: {error}',
                                                                       to_rabbit='on', to_mail='on')
                logging.info(f'Запрос {self.task} не валиден. Задание не принято в обработку')
        return valid_tasks

    @EXCEPTION_HANDLER.exception_decorator
    def main_process(self) -> None:
        self.db.clean_db()
        new_messages = self.rabbit.check_queue()
        valid_tasks = self.validator(new_messages)
        if valid_tasks:
            # Добавили новые задания в БД
            self.db.add_task_db(new_messages)
        # Получаем новые задания
        new_tasks = self.db.get_new_tasks()
        if new_tasks:
            logging.info(f'Получены задания со статусом Новое')
            self.run_process(self.eosdo_reg, new_tasks)

        monitoring_tasks = self.db.get_tasks_monitoring()
        if monitoring_tasks:
            logging.info(f'Получены задания со статусом Мониторинг:\n{monitoring_tasks}')
            self.run_process(self.eosdo_mon, monitoring_tasks)
        #
        eosdo_incoming_tasks = self.db.get_sending_tasks()
        if eosdo_incoming_tasks:
            logging.info(f'Начинаю мониторинг вх.документов в ЕОСДО')
            self.run_process(self.eosdo_res, eosdo_incoming_tasks)
        # Проверка почты
        eh = ErrorHandler('self.sender.receiving()', cfg, minutes_wait=5)
        while True:
            with eh:
                self.sender.receiving()
                break

    def prepare_tasks(self, tasks: list) -> dict:
        """
        Метод работает только по агрегированным заданиям по организации
        return {'организация А':['33765675', 388-3434], 'организация Б':['33765675', 388-3434],}
        """
        tasks_organization = {}
        organization = ''
        for task in tasks:
            if task[1].strip() != organization:
                organization = task[1].strip()
                tasks_organization[organization] = []
                tasks_organization[organization].append(task[0])
            else:
                tasks_organization[organization].append(task[0])
        return tasks_organization

    def run(self):
        eh = ErrorHandler('run', cfg)
        with eh:
            while True:
                self.main_process()


if __name__ == '__main__':
    log.set_1(cfg)
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
    })

    logging.info('\n\n=== Start ===\n\n')
    logging.info(f'Режим запуска: {cfg.mode}')
    task_finder = TaskFinder()
    task_finder.run()
