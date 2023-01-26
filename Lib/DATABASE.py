import logging
import time
import json
import base64
import psycopg2
from CONFIG import Config as cfg
import logging
from datetime import datetime
from psycopg2.extras import Json, RealDictCursor
import os

class DateBase:
    def __init__(self):
        self.login = cfg.db_login
        self.password = cfg.db_password
        self.connection = None

    def connect(self, type_cursor=None, max_tries=5):
        try:
            max_tries -= 1
            self.connection = psycopg2.connect(dbname=cfg.db_name, user=cfg.db_login, password=cfg.db_password,
                                               host=cfg.db_server, port=cfg.db_port)
            if type_cursor == 'dict':
                self.cursor = self.connection.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
            else:
                self.cursor = self.connection.cursor()
            return self.connection
        except Exception:
            if max_tries == 0:
                logging.error('Ошибка при подключении к БД. Попытки подключения исчерпаны')
                raise
            else:
                logging.error('Ошибка при подключении к БД. Пробую повторную попытку')

    def close(self):
        if self.connection is not None:
            self.connection.close()
        else:
            logging.info('Не могу закрыть connection, т.к. не был открыт')

    def get_one(self, task_id, column, type_response):
        """
        Получение результата из столбца по task_id
        :param task_id:
        :param column:
        :param type_response: тип курсора.
        :return:
        """
        query = f"SELECT {column} FROM TASKS_427 WHERE НОМЕР_ЗАПРОСА = '{task_id}'"
        if type_response == 'dict':
            with self.connect(type_cursor=type_response):
                self.cursor.execute(query)
                response = self.cursor.fetchone()[column]
        elif type_response == 'tuple':
            with self.connect():
                self.cursor.execute(query)
                response = self.cursor.fetchone()
        return response

    def create_sogl_db(self, task_id, data):
        """
        Записываю в БД лист согласования
        :param task_id: номер запроса
        :param data: лист согласования в формате словаря
        :return:
        """
        with self.connect():
            self.cursor.execute(
                "UPDATE TASKS_427 SET ЛИСТ_СОГЛАСОВАНИЯ = %s "
                "WHERE НОМЕР_ЗАПРОСА = %s",
                (Json(data), task_id,)
            )

    def update_list_delivery(self, task, organization):
        """
        Запись статуса ответа от Поставщика
        :param task: номер запроса в БД
        :param organization: имя организации от которой получен ответ
        :return:
        """
        #получаем текущий список рассылки
        list_delivery = self.get_one(task, 'СПИСОК_РАССЫЛКИ', 'dict')
        # записываем статус 'получен'
        list_delivery[organization]['статус'] = 'получен'
        no_answer = False
        try:
            data_json = json.dumps(list_delivery, indent=2, ensure_ascii=False)
            self.do_change_db(task, {'СПИСОК_РАССЫЛКИ': data_json})
        except KeyError as err:
            logging.error(f'В запросе {task} в СПИСКЕ_РАССЫЛКИ не найдено предприятие {organization}: {err}')
            raise
        for organization in list_delivery:
            if list_delivery[organization]['статус'] == 'отправлено':
                no_answer = True
        if no_answer == False:
            logging.info(f'По запросу {task} получены ответы от всех предприятий. Записываю в БД статус Закрыт')
            self.do_change_db(task, {'СТАТУС': 'Закрыт'})

    def do_change_db(self, tasks, column_value=None):
        """
        column_value = {'СТАТУС_ЕОСДО':'Согласование', 'РЕГ_НОМЕР':'22/1111'}
        """
        time_processing = datetime.now()
        params = ''

        if column_value:
            for column, value in column_value.items():
                params = f"{params} {column} = '{value}',"
        query = f"UPDATE TASKS_427 SET{params} ДАТА_ОБРАБОТКИ = '{time_processing}' WHERE НОМЕР_ЗАПРОСА = '{tasks}'"
        with self.connect():
            #только для случаев обновления ДАТЫ _ОБРАБОТКИ
            if isinstance(tasks, list):
                for task in tasks:
                    query = f"UPDATE TASKS_427 SET{params} " \
                            f"ДАТА_ОБРАБОТКИ = '{time_processing}' WHERE НОМЕР_ЗАПРОСА = '{task}'"
                    self.cursor.execute(query)
            else:
                self.cursor.execute(query)
        logging.info(f'Изменения в БД внесены')


    def add_delivery_list(self, task_id, data):
        """
        Добавить список рассылки в БД для определенной записи
        :param task_id: номер запроса
        :param data: словарь формата
        {
          "АО «ТВЭЛ»": {
            "mail": "mail@mail@ru",
            "type": "отрослевая",
            "response_status": ""
          }
        }
        :return:
        """
        with self.connect():
            self.cursor.execute(
                "UPDATE TASKS_427 SET СПИСОК_РАССЫЛКИ = %s "
                "WHERE НОМЕР_ЗАПРОСА = %s",
                (Json(data), task_id,)
            )

    def add_task_db(self, tasks):
        """
        Добавить новую запись в БД
        :param tasks: список из словарей формата [{'header': {requestID:''}, 'body':{}},
        {'header': {requestID:''}, 'body':{}}]
        :return:
        """
        status = 'Новое'
        with self.connect():
            for task in tasks:
                task_id = task['header']['requestID']
                organization = task['body']['organization']
                initiator = task['body']['initiator']
                request = task
                time_processing = datetime.now()
                self.cursor.execute(
                    "INSERT INTO TASKS_427 "
                    "("
                    "НОМЕР_ЗАПРОСА, "
                    "ОРГАНИЗАЦИЯ, "
                    "ИНИЦИАТОР, "
                    "ЗАПРОС, "
                    "ДАТА_ОБРАБОТКИ, "
                    "СТАТУС "
                    ") "
                    "VALUES (%s, %s, %s, %s, %s, %s)",
                    (task_id, organization, initiator, Json(request), time_processing, status,)
                )
        logging.info('Новые задания добавлены в БД')

    def get_new_tasks(self):
        """
        Получение записей со статусом Новое
        :return: Возвращает НОМЕР_ЗАПРОСА в формате [(1,), (2,)]
        """
        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor):
                self.cursor.execute(
                    "SELECT НОМЕР_ЗАПРОСА, ОРГАНИЗАЦИЯ FROM TASKS_427 WHERE "
                    "СТАТУС = 'Новое' AND ОШИБКИ IS NULL ORDER BY ОРГАНИЗАЦИЯ")
                tasks = self.cursor.fetchall()
        return tasks

     def clean_db(self):
        """
        Удаление из тиблицы tasks_427 записей со статусом Закрыт и датой обработки более cfg.last_day дней
        Удаление из тиблицы responses_427 записей c датой обработки более cfg.last_day дней
        :return:
        """
        date_now = datetime.now()
        with self.connect():
            query = "DELETE FROM TASKS_427 WHERE " \
                    f"EXTRACT(day FROM '{date_now}' - ДАТА_ОБРАБОТКИ) >= {cfg.last_day} AND СТАТУС = 'Закрыт'"
            self.cursor.execute(query)

            query = "DELETE FROM RESPONSES_427 WHERE " \
                    f"EXTRACT(day FROM '{date_now}' - ОТПРАВЛЕНО) >= {cfg.last_day}"
            self.cursor.execute(query)

    def get_tasks_monitoring(self, organization=None):
        """
        Получить записи со статусом Мониторинг и датой обработки более 60 мин
        Если Организация не задана, результат будет сгруппирован по организациям
        :param organization: имя организации
        :return:
        """

        date_now = datetime.now()
        with self.connect():
            if organization is not None:
                query = f"SELECT НОМЕР_ЗАПРОСА FROM TASKS_427 WHERE " \
                        f"EXTRACT(epoch FROM age('{date_now}', ДАТА_ОБРАБОТКИ))/60 >= {cfg.check_min} " \
                        f"AND СТАТУС = 'Мониторинг' " \
                        f"AND ОРГАНИЗАЦИЯ = '{organization}'" \
                        f"AND ОШИБКИ IS NULL"

            elif organization is None:
                query = f"SELECT НОМЕР_ЗАПРОСА, ОРГАНИЗАЦИЯ FROM TASKS_427 WHERE " \
                        f"EXTRACT(epoch FROM age('{date_now}', ДАТА_ОБРАБОТКИ))/60 >= {cfg.check_min}" \
                        f"AND СТАТУС = 'Мониторинг' " \
                        f"AND ОШИБКИ IS NULL " \
                        f"ORDER BY ОРГАНИЗАЦИЯ" \

            self.cursor.execute(query)
            tasks = self.cursor.fetchall()
        return tasks

    def response_db(self, task_response, response, desc, task_request):
        time_processing = datetime.now()
        with self.connect():
            self.cursor.execute(
                "INSERT INTO RESPONSES_427 "
                "("
                "НОМЕР_ОТВЕТА, "
                "ОТВЕТ, "
                "ОПИСАНИЕ, "
                "НОМЕР_ЗАПРОСА, "
                "ОТПРАВЛЕНО "
                ") "
                "VALUES (%s, %s, %s, %s, %s)",
                (task_response, Json(response), desc, task_request, time_processing,)
            )
            logging.info('Запись в таблицу RESPONSES_427 внесена')

    def create_table_tasks(self):
        """"
        Создание таблицы в БД
        """
        with self.connect():
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS TASKS_427  
                                 (НОМЕР_ЗАПРОСА VARCHAR PRIMARY KEY,
                                 ОРГАНИЗАЦИЯ TEXT NOT NULL,
                                 ИНИЦИАТОР TEXT NOT NULL,
                                 ЗАПРОС JSONB NOT NULL,
                                 НОМЕР_ПРОЕКТА TEXT,
                                 ДАТА_ПРОЕКТА DATE,
                                 СТАТУС_ЕОСДО TEXT,
                                 ЛИСТ_СОГЛАСОВАНИЯ JSONB,
                                 РЕГ_НОМЕР TEXT,
                                 ДАТА_РЕГ DATE,
                                 ССЫЛКА TEXT,
                                 СПИСОК_РАССЫЛКИ JSONB,
                                 СПОСОБ_ОТПРАВКИ TEXT,
                                 ДАТА_ОБРАБОТКИ TIMESTAMP NOT NULL,
                                 СТАТУС TEXT NOT NULL, 
                                 ОШИБКИ TEXT
                                 ); '''
                                )

    def create_table_respond(self):
        with self.connect():
            self.cursor.execute('''CREATE TABLE IF NOT EXISTS RESPONSES_427  
                                 (НОМЕР_ОТВЕТА VARCHAR PRIMARY KEY,
                                 ОТВЕТ JSONB NOT NULL,
                                 ОПИСАНИЕ TEXT NOT NULL,
                                 НОМЕР_ЗАПРОСА VARCHAR NOT NULL,
                                 ОТПРАВЛЕНО TIMESTAMP NOT NULL
                                 ); '''
                                )

    def update_date(self, tasks):
        """
        Обновление даты обработки записей
        :param tasks:
        :return:
        """
        with self.connect():
            time_processing = datetime.now()
            if isinstance(tasks, list):
                for task in tasks:
                    self.cursor.execute(
                        "UPDATE TASKS_427 SET ДАТА_ОБРАБОТКИ = %s "
                        "WHERE НОМЕР_ЗАПРОСА = %s",
                        (time_processing, task,)
                    )
            else:
                self.cursor.execute(
                    "UPDATE TASKS_427 SET ДАТА_ОБРАБОТКИ = %s "
                    "WHERE НОМЕР_ЗАПРОСА = %s",
                    (time_processing, tasks,)
                )

    def get_sending_tasks(self, organization=None):
        """
        Получение записей из БД со статусом Отправлено, способами отправки 'сешанный' или 'еосдо' и датой обработки
        более 120 мин
        :param organization: имя организации
        :return:
        """
        date_now = datetime.now()
        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor):
                if organization:
                    self.cursor.execute(
                        "SELECT НОМЕР_ЗАПРОСА "
                        "FROM TASKS_427 "
                        "WHERE "
                        "EXTRACT(epoch FROM age(%s, ДАТА_ОБРАБОТКИ))/120 >= %s"
                        "AND "
                        "СТАТУС = 'Отправлено'"
                        "AND "
                        "ОРГАНИЗАЦИЯ = %s "
                        "AND "
                        "(СПОСОБ_ОТПРАВКИ = 'смешанный' OR СПОСОБ_ОТПРАВКИ = 'еосдо')",
                        (date_now, cfg.check_min, organization,)
                    )
                    tasks = [task[0] for task in self.cursor.fetchall()]

                elif organization is None:
                    self.cursor.execute(
                        "SELECT НОМЕР_ЗАПРОСА, ОРГАНИЗАЦИЯ "
                        "FROM TASKS_427 "
                        "WHERE "
                        "EXTRACT(epoch FROM age(%s, ДАТА_ОБРАБОТКИ))/60 >= %s"
                        "AND "
                        "СТАТУС = 'Отправлено'"
                        "AND "
                        "(СПОСОБ_ОТПРАВКИ = 'смешанный' OR СПОСОБ_ОТПРАВКИ = 'еосдо')"
                        "ORDER BY ОРГАНИЗАЦИЯ",
                        (date_now, cfg.check_min,)
                    )
                    tasks = self.cursor.fetchall()
        return tasks

    def drop_table_tasks(self):
        with self.connect():
            self.cursor.execute("DROP TABLE tasks_427;")

    def drop_table_response(self):
        with self.connect():
            self.cursor.execute("DROP TABLE RESPONSES_427;")


if __name__ == '__main__':
    dict = {
        'a':'b'
    }

    list_sogl = json.dumps(dict, indent=4, ensure_ascii=False)
    db = DateBase()
    # db.drop_table_tasks()
    # db.create_table_tasks()
    db.clean_db()
    # db.response_db('93GnYRx', {'data':'data'}, 'ПРОЕКТ_СОЗДАН',  1000333)
    # db.add_reg_project('199-80', '22-9.2/18', '24.11.2022')
    # db.get_new_tasks()
    # db.drop_table()
    # db.create_table()

    # db.get_one('1000333', 'ЗАПРОС', 'dict')
    # db.get_task('РЕГ_НОМЕР', '22-9.2/25')


    # db.get_sogl_db('199000')
    # db.add_sogl_db('199000', data)
    # for key in [{'organization': 'АО"Гринатом"', 'task_id': '434f-567'},
    #             {'organization': 'АО"Атомэнергопроект"', 'task_id': '434f-411'},
    #             {'organization': 'АО "АСЭ"', 'task_id': '434f-4980000'},
    #             {'organization': 'АО "ТВЭЛ"', 'task_id': '434f-4777'}
    #             ]:
    #     db.add_task(key['task_id'], key['organization'])
    # db.get_tasks_monitoring("АО \"Гринатом\"")
    # body_task = db.get_one('1000333', 'ЗАПРОС', 'dict')
    # files_task = body_task["files"]
    # for file in files_task:
    #     with open(os.path.join(cfg.saved_files, file['file_name']), "wb") as newfile:
    #         newfile.write(base64.b64decode(file["file"]))

