import logging
import time
import json
import base64
import pandas as pd
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

    def get_task(self, column, value):
        """
        Получить номер запроса записи в БД
        :param column: имя столбца
        :param value: значение столбца
        :return:
        """
        query = f"SELECT НОМЕР_ЗАПРОСА FROM {cfg.table_tasks} WHERE {column} = '{value}'"
        with self.connect():
            self.cursor.execute(query)
            task = self.cursor.fetchone()[0]
        return task

    def get_status_task(self, theme):
        query = f"SELECT СТАТУС FROM {cfg.table_tasks} WHERE ТЕМА_ПИСЬМА = '{theme}'"
        with self.connect():
            self.cursor.execute(query)
            task = self.cursor.fetchone()[0]
        return task

    def get_one(self, task_id, column, table):
        """
        Получение результата из столбца по task_id
        :param task_id:
        :param column:
        :param type_response: тип курсора.
        :return:
        """
        query = f"SELECT {column} FROM {table} WHERE НОМЕР_ЗАПРОСА = '{task_id}'"
        with self.connect(type_cursor='dict'):
            self.cursor.execute(query)
            response = self.cursor.fetchone()[column]
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
                f"UPDATE {cfg.table_tasks} SET ЛИСТ_СОГЛАСОВАНИЯ = %s "
                "WHERE НОМЕР_ЗАПРОСА = %s",
                (Json(data), task_id,)
            )

    def do_change_db(self, tasks, table, column_value=None):
        """
        column_value = {'СТАТУС_ЕОСДО':'Согласование', 'РЕГ_НОМЕР':'22/1111'}
        """
        time_processing = datetime.now()
        params = ''

        if column_value:
            for column, value in column_value.items():
                params = f"{params} {column} = '{value}',"
        query = f"UPDATE {table} SET{params} ДАТА_ОБРАБОТКИ = '{time_processing}' WHERE НОМЕР_ЗАПРОСА = '{tasks}'"
        with self.connect():
            # только для случаев обновления ДАТЫ _ОБРАБОТКИ
            if isinstance(tasks, list):
                for task in tasks:
                    query = f"UPDATE {table} SET{params} " \
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
        time_processing = datetime.now()
        with self.connect():
            self.cursor.execute(
                f"UPDATE {cfg.table_tasks} SET СПИСОК_РАССЫЛКИ = %s, "
                f"ОТПРАВЛЕНО = %s "
                "WHERE НОМЕР_ЗАПРОСА = %s",
                (Json(data), time_processing, task_id,)
            )

    def add_project_db(self, task, project, date_project, list_sogl, link, status):
        time_processing = datetime.now()
        with self.connect():
            self.cursor.execute(
                f"INSERT INTO {cfg.table_eosdo} "
                "("
                "НОМЕР_ЗАПРОСА, "
                "НОМЕР_ПРОЕКТА, "
                "ДАТА_ПРОЕКТА, "
                "ЛИСТ_СОГЛАСОВАНИЯ, "
                "ССЫЛКА, "
                "СТАТУС_ЕОСДО, "
                "ДАТА_ОБРАБОТКИ"
                ") "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (task, project, date_project, list_sogl, link, status, time_processing,)
            )
            logging.info('Запись в таблицу EOSDO_427 внесена')

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
                task_life = task['body']['task_life']
                time_processing = datetime.now()
                self.cursor.execute(
                    f"INSERT INTO {cfg.table_tasks} "
                    "("
                    "НОМЕР_ЗАПРОСА, "
                    "ОРГАНИЗАЦИЯ, "
                    "ИНИЦИАТОР, "
                    "ЗАПРОС, "
                    "СРОК_ДЕЙСТВИЯ, "
                    "ДАТА_ОБРАБОТКИ, "
                    "СТАТУС "
                    ") "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    (task_id, organization, initiator, Json(request), task_life, time_processing, status,)
                )
        logging.info('Новые задания добавлены в БД')

    def get_new_tasks(self) -> list:
        """
        Получение записей со статусом Новое
        :return: Возвращает НОМЕР_ЗАПРОСА в формате [(1,), (2,)]
        """
        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor):
                self.cursor.execute(
                    f"SELECT НОМЕР_ЗАПРОСА, ОРГАНИЗАЦИЯ FROM {cfg.table_tasks} WHERE "
                    "СТАТУС = 'Новое' AND ОШИБКИ IS NULL ORDER BY ОРГАНИЗАЦИЯ")
                tasks = self.cursor.fetchall()
        return tasks

    def clean_db(self):
        """
        Удаление из таблицы tasks_427 записей со истекшим сроком действия ТКП
        Удаление из таблицы responses_427 записей c датой обработки более cfg.last_day дней
        :return:
        """
        from b_lib.b_excel import Excel
        date_now = datetime.now()
        with self.connect():
            # если истек срок действия ТКП, закрываем задание
            query = "UPDATE TASKS_427 SET СТАТУС = 'Закрыт' WHERE " \
                    f"СРОК_ДЕЙСТВИЯ < DATE_PART('day', '{date_now}' - ОТПРАВЛЕНО) AND СТАТУС = 'Отправлено'"
            self.cursor.execute(query)
            # Задания для удаления из таблицы TASKS
            query = f"SELECT * FROM {cfg.table_tasks} WHERE " \
                    f"DATE_PART('day', '{date_now}' - ДАТА_ОБРАБОТКИ) >= {cfg.last_day} AND " \
                    f"СТАТУС = 'Закрыт'"
            df = pd.read_sql(query, self.connection)
            if df.empty is False:
                # Записываем в файл
                Excel().write_to_excel(cfg.removed_tasks, df)
                tasks = df['НОМЕР_ЗАПРОСА'].tolist()
                # Задания для удаления из таблицы eosdo [task1, task2] превращаем в (task1, task2)
                tasks_set = str(tasks).replace('[', '(').replace(']', ')')
                query = f"SELECT * FROM {cfg.table_eosdo} WHERE НОМЕР_ЗАПРОСА IN {tasks_set}"
                df = pd.read_sql(query, self.connection)
                # Записываем их в файл
                Excel().write_to_excel(cfg.removed_eosdo, df)
                # Удаляем данные из БД
                query = f"DELETE FROM {cfg.table_tasks} WHERE НОМЕР_ЗАПРОСА IN {tasks_set}"
                self.cursor.execute(query)

            # Задания для удаления из таблицы RESPONSES
            query = f"SELECT * FROM RESPONSES_427 WHERE " \
                    f"DATE_PART('day', '{date_now}' - ОТПРАВЛЕНО) >= {cfg.last_day_response}"
            df = pd.read_sql(query, self.connection)
            if df.empty is False:
                Excel().write_to_excel(cfg.removed_responses, df)
                query = f"DELETE FROM {cfg.table_responses} WHERE " \
                        f"EXTRACT(day FROM '{date_now}' - ОТПРАВЛЕНО) >= {cfg.last_day_response}"
                self.cursor.execute(query)

    def remove_task(self, task):
        with self.connect():
            query = f"DELETE FROM {cfg.table_tasks} WHERE НОМЕР_ЗАПРОСА = '{task}'"
            self.cursor.execute(query)

        with self.connect():
            query = f"DELETE FROM {cfg.table_eosdo} WHERE НОМЕР_ЗАПРОСА = '{task}'"
            self.cursor.execute(query)

    def get_tasks_monitoring(self, organization=None):
        """
        Получить записи со статусом Мониторинг и датой обработки более 60 мин
        Если Организация не задана, результат будет сгруппирован по организациям
        :param organization: имя организации
        :return:
        """

        date_now = datetime.now()
        root_query = f"SELECT НОМЕР_ЗАПРОСА, ОРГАНИЗАЦИЯ FROM {cfg.table_tasks} WHERE " \
                     f"EXTRACT(epoch FROM age('{date_now}', ДАТА_ОБРАБОТКИ))/60 >= {cfg.check_min} " \
                     f"AND СТАТУС = 'Мониторинг' " \
                     "AND ОШИБКИ IS NULL "
        with self.connect():
            if organization:
                query = root_query + f"AND ОРГАНИЗАЦИЯ = '{organization}'"
            else:
                query = root_query + f"ORDER BY ОРГАНИЗАЦИЯ"
            self.cursor.execute(query)
            tasks = self.cursor.fetchall()
        return tasks

    def add_error(self, task_id, type_error):
        time_processing = datetime.now()
        with self.connect():
            self.cursor.execute(
                f"UPDATE {cfg.table_tasks} SET "
                "ОШИБКИ = %s, "
                "ДАТА_ОБРАБОТКИ = %s "
                "WHERE НОМЕР_ЗАПРОСА = %s",
                (type_error, time_processing, task_id,)
            )

    def response_db(self, task_response, response, desc, task_request):
        time_processing = datetime.now()
        with self.connect():
            self.cursor.execute(
                f"INSERT INTO {cfg.table_responses} "
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
            self.cursor.execute(f'''CREATE TABLE IF NOT EXISTS {cfg.table_tasks}  
                                 (НОМЕР_ЗАПРОСА VARCHAR PRIMARY KEY,
                                 ОРГАНИЗАЦИЯ TEXT NOT NULL,
                                 ИНИЦИАТОР TEXT NOT NULL,
                                 ЗАПРОС JSONB NOT NULL,
                                 СПОСОБ_ОТПРАВКИ TEXT,
                                 ТЕМА_ПИСЬМА TEXT,
                                 СПИСОК_РАССЫЛКИ JSONB,
                                 ОТПРАВЛЕНО TIMESTAMP,
                                 СТАТУС TEXT NOT NULL,
                                 СРОК_ДЕЙСТВИЯ INTEGER NOT NULL,
                                 ДАТА_ОБРАБОТКИ TIMESTAMP NOT NULL,
                                 ОШИБКИ TEXT
                                 ); '''
                                )

            self.cursor.execute(f'''CREATE INDEX TASKS_TABLE ON {cfg.table_tasks} 
                                    (ОРГАНИЗАЦИЯ, ИНИЦИАТОР, ДАТА_ОБРАБОТКИ, СТАТУС, 
                                    ОШИБКИ, СПОСОБ_ОТПРАВКИ,
                                    СПИСОК_РАССЫЛКИ, СРОК_ДЕЙСТВИЯ
                                 ); '''
                                )

    def create_table_eosdo(self):
        """"
        Создание таблицы в БД
        """
        with self.connect():
            self.cursor.execute(f'''CREATE TABLE IF NOT EXISTS {cfg.table_eosdo}   
                                 (
                                 ID SERIAL PRIMARY KEY,
                                 НОМЕР_ЗАПРОСА VARCHAR,
                                 НОМЕР_ПРОЕКТА TEXT,
                                 ДАТА_ПРОЕКТА DATE,
                                 ЛИСТ_СОГЛАСОВАНИЯ JSONB,
                                 РЕГ_НОМЕР TEXT,
                                 ДАТА_РЕГ DATE,
                                 СТАТУС_ЕОСДО TEXT,
                                 ССЫЛКА TEXT,
                                 ДАТА_ОБРАБОТКИ TIMESTAMP NOT NULL,
                                 FOREIGN KEY (НОМЕР_ЗАПРОСА) REFERENCES TASKS_427 (НОМЕР_ЗАПРОСА) ON DELETE CASCADE
                                 ); '''
                                )

            self.cursor.execute(f'''CREATE INDEX EOSDO_TABLE ON {cfg.table_eosdo} 
                                    (
                                    НОМЕР_ПРОЕКТА, РЕГ_НОМЕР, СТАТУС_ЕОСДО, ДАТА_ОБРАБОТКИ
                                 ); '''
                                )

    def create_table_respond(self):
        with self.connect():
            self.cursor.execute(f'''CREATE TABLE IF NOT EXISTS {cfg.table_responses}    
                                 (НОМЕР_ОТВЕТА VARCHAR PRIMARY KEY,
                                 ОТВЕТ JSONB NOT NULL,
                                 ОПИСАНИЕ TEXT NOT NULL,
                                 НОМЕР_ЗАПРОСА VARCHAR,
                                 ОТПРАВЛЕНО TIMESTAMP NOT NULL
                                 ); '''
                                )
            self.cursor.execute(f'''CREATE INDEX RESPONSE_TABLE ON  {cfg.table_responses}  
                                                (ОТПРАВЛЕНО, НОМЕР_ЗАПРОСА
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
                        f"UPDATE {cfg.table_tasks} SET ДАТА_ОБРАБОТКИ = %s "
                        "WHERE НОМЕР_ЗАПРОСА = %s",
                        (time_processing, task,)
                    )
            else:
                self.cursor.execute(
                    f"UPDATE {cfg.table_tasks} SET ДАТА_ОБРАБОТКИ = %s "
                    "WHERE НОМЕР_ЗАПРОСА = %s",
                    (time_processing, tasks,)
                )

    def get_sending_tasks(self, organization=None):
        """
            Получение записей из БД со статусом Отправлено, способами отправки 'сешанный' или 'еосдо' и датой обработки больше 60 мин
           :param organization: имя организации
           :return:
            """
        date_now = datetime.now()
        root_query = "SELECT НОМЕР_ЗАПРОСА, ОРГАНИЗАЦИЯ " \
                     f"FROM {cfg.table_tasks} " \
                     f"WHERE EXTRACT(epoch FROM age('{date_now}', ДАТА_ОБРАБОТКИ))/60 >= {cfg.check_min} " \
                     "AND СТАТУС = 'Отправлено' " \
                     "AND (СПОСОБ_ОТПРАВКИ = 'смешанный' OR СПОСОБ_ОТПРАВКИ = 'еосдо') " \
                     "AND ОШИБКИ IS NULL "

        with self.connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor):
                if organization:
                    query = root_query + f"AND ОРГАНИЗАЦИЯ = '{organization}'"
                    self.cursor.execute(query)
                    tasks = [task[0] for task in self.cursor.fetchall()]

                else:
                    query = root_query + 'ORDER BY ОРГАНИЗАЦИЯ'
                    self.cursor.execute(query)
                    tasks = self.cursor.fetchall()
        return tasks

    def drop_table_tasks(self):
        with self.connect():
            self.cursor.execute(f"DROP TABLE {cfg.table_tasks};")

    def drop_table_respond(self):
        with self.connect():
            self.cursor.execute(f"DROP TABLE {cfg.table_responses};")

    def drop_table_eosdo(self):
        with self.connect():
            self.cursor.execute(f"DROP TABLE {cfg.table_eosdo};")


if __name__ == '__main__':
    dict = {
        'a': 'b'
    }

    db = DateBase()
    db.clean_db()
    # db.drop_table_eosdo()
    # db.create_table_tasks()
    # db.create_table_eosdo()
    # # db.drop_table_tasks()
    #
    # # db.drop_table_respond()
    # db.create_table_respond()

    # db.create_table_tasks()

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
