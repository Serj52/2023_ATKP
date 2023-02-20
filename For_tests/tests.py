import json
import os.path
import time
from datetime import datetime
from For_tests.EOSDOEMPLOYEE import business_greenatom, business_atom
from b_lib.b_post import BusinessPost
from pathlib import Path
from b_lib.RABBIT import Rabbit
from sender import Sender
from CONFIG import Config as cfg
from Taskfinder import TaskFinder
from b_lib.DATABASE import DateBase
from eosdoreg import EosdoReg, EosdoMon

class TestEosdoReg:

    def get_request(self, name_file):
        path = os.path.join(cfg.folder_root, 'For_tests', f'{name_file}')
        with open(path, mode='r', encoding='utf-8') as file:
            request = json.load(file)
            return request

    def test_validator(self):
        #Позитивный случай
        request = self.get_request('request_green.json')
        valid_tasks = TaskFinder().validator([request])
        assert valid_tasks != []

        #Негативный случай
        request = self.get_request('bad_request_2.json')
        valid_tasks = TaskFinder().validator([request])
        assert valid_tasks == []
        #проверяем, что уведомление ушло в очередь
        response = Rabbit().check_queue('rpa.errors')[0]
        assert response["header"]["id"] != ""
        assert response["header"]["date"] != ""
        assert 'Запрос не валиден' in response["ErrorText"]

        #Негативный случай
        request = self.get_request('bad_request_1.json')
        valid_tasks = TaskFinder().validator([request])
        assert valid_tasks == []
        #проверяем, что уведомление ушло в очередь
        response = Rabbit().check_queue('goodbay')[0]
        assert response["header"]["id"] != ""
        # assert response["header"]["sourceId"] != ""
        assert response["header"]["date"] != ""
        assert 'Запрос не валиден' in response["ErrorText"]

    def test_add_task_db(self):
        """Тестрирование записи в БД новых заданий"""
        request = self.get_request('request_green.json')
        DateBase().remove_task(request['header']['requestID'])
        DateBase().add_task_db([request])
        task = DateBase().get_one(request['header']['requestID'], 'НОМЕР_ЗАПРОСА', 'TASKS_427')
        organization = DateBase().get_one(request['header']['requestID'], 'ОРГАНИЗАЦИЯ', 'TASKS_427')
        initiator = DateBase().get_one(request['header']['requestID'], 'ИНИЦИАТОР', 'TASKS_427')
        task_body = DateBase().get_one(request['header']['requestID'], 'ЗАПРОС', 'TASKS_427')
        date_update = DateBase().get_one(request['header']['requestID'], 'ДАТА_ОБРАБОТКИ', 'TASKS_427')
        status = DateBase().get_one(request['header']['requestID'], 'СТАТУС', 'TASKS_427')
        assert request['header']['requestID'] == task
        assert request['body']['organization'] == organization
        assert request['body']['initiator'] == initiator
        assert task_body != None
        assert date_update != None
        assert status == 'Новое'
        DateBase().remove_task(request['header']['requestID'])

    def test_create_doc(self, task='request_green.json'):
        #Создаем документ в БД
        request = self.get_request(task)
        DateBase().remove_task(request['header']['requestID'])
        DateBase().add_task_db([request])
        task_id = request['header']['requestID']
        queue = request['header']['replayRoutingKey']
        organization = request['body']['organization']
        EosdoReg().start_process([task_id], organization)
        #Проверка заполнения новыми данными в БД
        assert DateBase().get_one(task_id, 'СПИСОК_РАССЫЛКИ', 'TASKS_427') != None
        assert DateBase().get_one(task_id, 'СПОСОБ_ОТПРАВКИ', 'TASKS_427') != None
        assert DateBase().get_one(task_id, 'СТАТУС', 'TASKS_427') == 'Мониторинг'
        assert DateBase().get_one(task_id, 'ОШИБКИ', 'TASKS_427') == None

        assert DateBase().get_one(task_id, 'ССЫЛКА', 'EOSDO_427') != None
        assert DateBase().get_one(task_id, 'НОМЕР_ПРОЕКТА', 'EOSDO_427') != None
        assert DateBase().get_one(task_id, 'ДАТА_ПРОЕКТА', 'EOSDO_427') != None
        assert DateBase().get_one(task_id, 'СТАТУС_ЕОСДО', 'EOSDO_427') != None
        assert DateBase().get_one(task_id, 'ЛИСТ_СОГЛАСОВАНИЯ', 'EOSDO_427') != None
        assert DateBase().get_one(task_id, 'ДАТА_ОБРАБОТКИ', 'EOSDO_427') != None
        time.sleep(10)
        # Проверка полноты данных переданных шину
        response = Rabbit().check_queue(queue)[0]
        assert response["header"]["id"] != ""
        assert response["header"]["sourceId"] != ""
        assert response["header"]["date"] != ""
        assert response["body"]["type"] == "регистрация"
        assert response["body"]["проект"] != ""
        assert response["body"]["ссылка"] != ""
        assert response["ErrorText"] == ''

    def test_send_sogl(self):
        # self.test_create_doc('request_green.json')
        request = self.get_request('request_green.json')
        task_id = request['header']['requestID']
        organization = request['body']['organization']
        queue = request['header']['replayRoutingKey']
        project = DateBase().get_one(task_id, 'НОМЕР_ПРОЕКТА', 'EOSDO_427')
        date = DateBase().get_one(task_id, 'ДАТА_ПРОЕКТА', 'EOSDO_427').strftime('%d.%m.%Y')
        # согласуем документ
        business_greenatom.Business().processing('согласование', project, date)
        #Мониторим
        EosdoMon().start_process([task_id], organization)
        #Проверяем БД
        assert DateBase().get_one(task_id, 'СТАТУС_ЕОСДО', 'EOSDO_427') == 'Согласование'
        assert DateBase().get_one(task_id, 'СТАТУС', 'TASKS_427') == 'Мониторинг'
        # Проверка полноты данных переданных шину
        response = Rabbit().check_queue(queue)[0]
        assert response["header"]["id"] != ""
        assert response["header"]["sourceId"] != ""
        assert response["header"]["date"] != ""
        assert response["body"]["type"] == "согласование"
        assert response["body"]["проект"] != ""
        assert response["body"]["лист_согласования"] != ""
        assert response["body"]["статус"] == "Согласование"
        assert response["ErrorText"] == ''

    def test_revision(self):
        for case in ['with_file', 'without_file']:
            self.test_create_doc('request_green.json')
            request = self.get_request('request_green.json')
            task_id = request['header']['requestID']
            organization = request['body']['organization']
            queue = request['header']['replayRoutingKey']
            project = DateBase().get_one(task_id, 'НОМЕР_ПРОЕКТА', cfg.table_eosdo)
            date = DateBase().get_one(task_id, 'ДАТА_ПРОЕКТА', cfg.table_eosdo).strftime('%d.%m.%Y')
            if case == 'with_file':
                #Делаем документ со статусом Доработка без файлов
                business_greenatom.Business().processing('доработка', project, date, True)
            else:
                # Делаем документ со статусом Доработка c файлами Отклонивших
                business_greenatom.Business().processing('доработка', project, date)
            # Проверяем статус
            EosdoMon().start_process([task_id], organization)
            # Проверяем БД
            assert DateBase().get_one(task_id, 'СТАТУС_ЕОСДО', cfg.table_eosdo) == 'Доработка'
            assert DateBase().get_one(task_id, 'СТАТУС', cfg.table_tasks) == 'Обработан'
            time.sleep(10)
            # Проверка полноты данных переданных шину
            response = Rabbit().check_queue(queue)[0]
            assert response["header"]["id"] != ""
            assert response["header"]["sourceId"] != ""
            assert response["header"]["date"] != ""
            assert response["body"]["type"] == "согласование"
            assert response["body"]["проект"] != ""
            assert response["body"]["лист_согласования"] != ""
            assert response["body"]["статус"] == "Доработка"
            assert response["ErrorText"] == ''
            #Проверяем, что в сообщении, отправленного в шину прикреплен файл отклонившего
            if case == 'with_file':
                assert response["body"]["лист_согласования"]["Контроль согласования"][0]["решение"] == 'Отклонено'
                assert response["body"]["лист_согласования"]["Контроль согласования"][0]["вложения"] != []

    def test_rejected_normocontroler(self):
        """
        Тест статуса документа Подтверждение отправки на подписание в ЕОСДО
        """
        for case in ['without_file']:
            self.test_create_doc('request_atom.json')
            request = self.get_request('request_atom.json')
            task_id = request['header']['requestID']
            organization = request['body']['organization']
            queue = request['header']['replayRoutingKey']
            project = DateBase().get_one(task_id, 'НОМЕР_ПРОЕКТА', cfg.table_eosdo)
            date = DateBase().get_one(task_id, 'ДАТА_ПРОЕКТА', cfg.table_eosdo).strftime('%d.%m.%Y')
            # Отклоняем документ Нормоконтролером
            if case == 'with_file':
                business_atom.Business().processing('подтверждение_отправки', project, date, True)
            else:
                business_atom.Business().processing('подтверждение_отправки', project, date)
            # Проверяем статус
            EosdoMon().start_process([task_id], organization)
            if case == 'with_file':
                # Проверяем БД
                assert DateBase().get_one(task_id, 'СТАТУС_ЕОСДО', cfg.table_eosdo) == 'Подтверждение отправки на подписание в ЕОСДО'
                assert DateBase().get_one(task_id, 'СТАТУС', cfg.table_tasks) == 'Мониторинг'
            else:
                # Проверяем БД
                assert DateBase().get_one(task_id, 'СТАТУС_ЕОСДО', cfg.table_eosdo) == 'Доработка'
                assert DateBase().get_one(task_id, 'СТАТУС', cfg.table_tasks) == 'Обработан'
                # Проверка полноты данных переданных шину
            time.sleep(10)
            response = Rabbit().check_queue(queue)[0]
            assert response["header"]["id"] != ""
            assert response["header"]["sourceId"] != ""
            assert response["header"]["date"] != ""
            assert response["body"]["type"] == "согласование"
            assert response["body"]["проект"] != ""
            assert response["body"]["лист_согласования"] != ""
            assert response["ErrorText"] == ''
            if case == 'with_file':
                assert response["body"]["статус"] == "Подтверждение отправки на подписание в ЕОСДО"
            else:
                assert response["body"]["статус"] == "Доработка"
            # Проверяем, что в сообщении, отправленного в шину прикреплен файл отклонившего
            assert response["body"]["лист_согласования"]["Нормоконтроль"][0]["решение"] == 'Замечания нормоконтролера'

    def test_close_project(self):
        # self.test_create_doc('request_green.json')
        request = self.get_request('request_green.json')
        task_id = request['header']['requestID']
        organization = request['body']['organization']
        queue = request['header']['replayRoutingKey']
        project = DateBase().get_one(task_id, 'НОМЕР_ПРОЕКТА', cfg.table_eosdo)
        date = DateBase().get_one(task_id, 'ДАТА_ПРОЕКТА', cfg.table_eosdo).strftime('%d.%m.%Y')
        # Согласовываем документ полностью
        business_greenatom.Business().processing('закрыт', project, date)
        # Проверяем статус
        EosdoMon().start_process([task_id], organization)
        # Проверяем БД
        reg_number = DateBase().get_one(task_id, 'РЕГ_НОМЕР', cfg.table_eosdo)
        date = DateBase().get_one(task_id, 'ДАТА_РЕГ', cfg.table_eosdo)
        theme_message = f'{reg_number.replace("/", "-", 1)}_{datetime.strftime(date, "%d.%m.%Y")}'
        assert DateBase().get_one(task_id, 'СТАТУС_ЕОСДО', cfg.table_eosdo) == 'Закрыт'
        assert DateBase().get_one(task_id, 'СТАТУС', cfg.table_tasks) == 'Отправлено'
        assert DateBase().get_one(task_id, 'ТЕМА_ПИСЬМА', cfg.table_tasks) == theme_message
        #проверка созданной папки внутри Receiving
        assert theme_message in [dir.name for dir in Path(cfg.folder_receiving).iterdir()]
        # Проверка полноты данных переданных шину
        time.sleep(10)
        response = Rabbit().check_queue(queue)[0]
        assert response["header"]["id"] != ""
        assert response["header"]["sourceId"] != ""
        assert response["header"]["date"] != ""
        assert response["body"]["type"] == "Рассылка"
        assert response["body"]["проект"] != ""
        assert response["body"]["reseivers_list"] != ""
        assert response["ErrorText"] == ''

    def test_get_message(self):
        # self.test_close_project()
        request = self.get_request('request_green.json')
        task_id = request['header']['requestID']
        queue = request['header']['replayRoutingKey']
        #Отправляем письмо от Контрагента. На момент отправки в Reseiving должна быть одна папка
        theme = DateBase().get_one(task_id, 'ТЕМА_ПИСЬМА', cfg.table_tasks)
        path_file = os.path.join(cfg.folder_root, 'doc', 'Описание ПР_запрос ТКП ЕОСДО 08.01.2023.docx')
        BusinessPost().send_mail(
            address='GREN-r-000427@Greenatom.ru',
            subject=theme,
            body='Ответ на ТКП',
            attachments=[path_file]
        )
        time.sleep(10)
        Sender().receiving()
        # Проверка полноты данных переданных шину
        time.sleep(10)
        response = Rabbit().check_queue(queue)[0]
        assert response["header"]["id"] != ""
        assert response["header"]["sourceId"] != ""
        assert response["header"]["date"] != ""
        assert response["body"]["поставщик"] != ""
        assert response["body"]["текст сообщения"] != ""
        assert response["body"]["номер"] != ""
        assert response["body"]["дата"] != ""
        assert response["body"]["files"] != []
        assert response["ErrorText"] == ''


















