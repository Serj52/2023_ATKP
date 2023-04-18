import logging.config
import logging
import json
from typing import Union
from collections import Counter
import time
import pyperclip
import uuid
from datetime import datetime
from CONFIG import Config as cfg
from selenium.webdriver.common.keys import Keys
import re
from selenium.common.exceptions import TimeoutException
from b_lib.b_eosdo import BusinessEosdo
from b_lib.b_eosdo import Selector
from b_lib.b_post import BusinessPost
from b_lib import EXCEPTION_HANDLER


class EosdoReceive(BusinessEosdo):
    def __init__(self, eosdo_instance=None, conection=None):
        super().__init__()
        self.unknown_document = []
        self.tasks = []
        if eosdo_instance:
            self.__dict__['eosdo'] = eosdo_instance
            self.connection = conection

    @EXCEPTION_HANDLER.exception_decorator
    def start_process(self, tasks: list, organization: str) -> None:
        """
        Проверка входящих документов в ЕОСДО
        :param tasks: список из номеров запросов со статусом Отправлено и способом отправки смешанный или еосдо
        :param organization: имя организации
        :return:
        """
        self.tasks = tasks
        if self.connection is False:
            try:
                self.open_eosdo(organization)
            except Exception:
                raise EXCEPTION_HANDLER.OpenEOSDOError('Ошибка при открытии ЕОСДО')
        try:
            self.main_process()
        except Exception as err:
            logging.error(f'Ошибка {err}')
            self.reconect_eosdo(organization)
            self.main_process()

    def main_process(self) -> None:
        # Проверяем наличие пришедших писем
        self.tools.clean_dir(cfg.saved_files)
        self.unknown_document = []
        # нажимаю Задачи/Уведомления
        self.eosdo.find_element("//a[text()='Задачи/Уведомления']").click()
        self.set_filter()
        if self.eosdo.exists_by_xpath(Selector.no_incoming, 5) is False:
            # настройка вывода по 100 документов на станице
            self.eosdo.find_element(Selector.amount_show_files, 5).click()
            self.eosdo.find_element(Selector.hundred, 30).click()
            # Получение числа Входящих документов
            incoming_documents = len(self.eosdo.find_elements(Selector.incoming_row))
            logging.info('Начинаю обработку вх документов в ЕОСДО')
            # Обрабатываем входящие документы
            start = 1
            while True:
                document = self.document_process(incoming_documents, self.tasks, start)
                # Если нашли совпадение, обновляем число входящих документов и продолжаем проверку
                # if response:
                if self.eosdo.exists_by_xpath(Selector.no_incoming, 5) is False and document:
                    # Обновляем число документов после обработанного и повторяем обработку
                    incoming_documents = len(self.eosdo.find_elements(Selector.incoming_row))
                    start = document
                else:
                    break
            if self.unknown_document:
                body = f'Нам прислали письмов ЕОСДО, которое не удалось идентифицировать. ' \
                       f'Просьба ознакомиться. Ссылки на документы: {self.unknown_document}'
                BusinessPost().send_mail(cfg.support_email, cfg.robot_name, body)
                logging.info('В поддержку направлено письмо о неизвестном письме в ЕОСДО')
        else:
            logging.info('Входящих писем в ЕОСДО нет')
            logging.info('Обработку вх документов в ЕОСДО закончил')
        # Записываем в базу данных дату проверки документов
        self.db.do_change_db(self.tasks, cfg.table_tasks)
        self.exit_eosdo()

    def document_process(self, incoming_documents: int, tasks: list, start: int) -> Union[bool, int]:
        for document in range(start, incoming_documents + 1):
            reg = ''
            reseived = ''
            summary = ''
            xpath_doc_row = f'//table[@id="InboxDataTable"]//tbody/tr[{document}]'
            time.sleep(1)
            try:
                reseived = self.eosdo.find_element(f'{xpath_doc_row}{Selector.received}', 5).text
                reg = self.eosdo.find_element(f'{xpath_doc_row}{Selector.xpath_reg_number}', 5).text
            except TimeoutException:
                pass
            logging.info(f'Открываю документ {reg} от {reseived}')
            self.eosdo.double_click(xpath_doc_row, 10)
            # Проверяем краткое содержание на предмет рег.номера
            try:
                summary = self.eosdo.find_element(Selector.text_area).text
            except Exception:
                pass
            # получаю ссылку на документ
            self.eosdo.find_element(Selector.link_project, 10).click()
            link = pyperclip.paste()
            # получаем отправителя данного письма
            try:
                # Отправитель письма
                time.sleep(2)
                sender = self.eosdo.find_element(Selector.sender, 10).text
            except TimeoutException:
                logging.info(f'Не найден Отправитель. Неизвестный входящий документ {reg} от {reseived}')
                self.eosdo.find_element(Selector.button_cansel, 3).click()
                self.unknown_document.append(link)
                continue
            found = self.check(tasks, summary, sender, link)
            if found is False:
                logging.info(f'Неизвестный входящий документ {reg} от {reseived}')
                self.unknown_document.append(link)
                self.eosdo.find_element(Selector.button_cansel, 20).click()
            else:
                return document
        return False

    def check(self, tasks: list, summary: str, sender: str, link: str) -> bool:
        # сначала поверяем все номера на первой вкладке
        count_page = 1
        while count_page <= 2:
            for index, task in enumerate(tasks):
                reg_number = self.db.get_one(task, 'РЕГ_НОМЕР', cfg.table_eosdo)
                if count_page == 1:
                    # Ищим рег номер документа в поле краткое содержание документа
                    if reg_number in summary:
                        logging.info(f'{reg_number} найден в поле Краткое содержание')
                        self.process_doc(task, index, sender, link, summary)
                        return True
                    # Ищим рег номер документа в именах прикрепленных файлов
                    elif self.eosdo.exists_by_xpath(f'{Selector.document_info}//label[contains(text(),"{reg_number}")]',
                                                    3):
                        logging.info(f'{reg_number} найден в Прикрепленных файлах')
                        self.process_doc(task, index, sender, link, summary)
                        return True
                elif count_page == 2:
                    # Ищим рег номер документа в связанных документах
                    time.sleep(1)
                    if self.eosdo.exists_by_xpath(
                            f'//table[@id="component11"]//span[contains(text(),"{reg_number}")]', 3):
                        logging.info(f'{reg_number} найден в Связанных документах')
                        self.eosdo.find_element(Selector.tab_main).send_keys(Keys.ENTER)
                        # self.eosdo.find_element(Selector.tab_main, 20).click()
                        self.process_doc(task, index, sender, link, summary)
                        return True
            count_page += 1
            # переходим во вкладку Связанные документы
            self.eosdo.find_element(Selector.tab_related_doc).send_keys(Keys.ENTER)
            time.sleep(1)
        return False

    def set_filter(self) -> None:
        if self.eosdo.exists_by_xpath(Selector.filter_apply) is False:
            # открываю типы документов
            self.eosdo.find_element(Selector.type_doc, 5).click()
            # выбираю входящие
            self.eosdo.find_element(Selector.incoming_doc, 1, 'on').click()
            # открываю типы задач
            self.eosdo.find_element(Selector.type_tasks, 5).click()
            # выбираю на рассмотрение
            self.eosdo.find_element(Selector.consideration, 1, 'on').click()
            # применяю
            self.eosdo.find_element(Selector.add_group).click()
            logging.info('Фильтр выставлен')

    def process_doc(self, task: str, index: int, sender: str, link: str, summary: str) -> None:
        """
        Обработка карточки документа
        :param task: номер запроса в БД
        :param index:
        :param link:
        :param summary:
        :param sender: отправитель
        :return:
        """
        # сохраняем номер и дату документа
        queue = self.db.get_one(task, 'ЗАПРОС', cfg.table_tasks)['header']['replayRoutingKey']
        text = self.eosdo.find_element(Selector.reg_number).text
        reg_number = re.findall(r'\d{1,}-\d{1,}\S{0,}\d{1,}', text)[0]
        date = re.findall(r'\d{2}.\d{2}.\d{4}', text)[0]
        files = len(self.eosdo.find_elements(Selector.amount_added_files_income, 30))
        self.export_files(cfg.saved_files, files)

        with open(cfg.response_incoming_mail, 'r', encoding='utf-8') as file:
            data = json.load(file)
        data['header']['requestID'] = responseid = str(uuid.uuid4())
        data['header']['sourceId'] = task
        data['header']['date'] = str(datetime.now())
        data['body']['поставщик'] = sender
        data['body']['cсылка'] = link
        data["code"] = 1011
        data['body']['номер'] = reg_number
        data['body']['дата'] = date
        data['body']['текст сообщения'] = summary
        data['body']['files'] = self.tools.encode_base64(cfg.saved_files)
        data_json = json.dumps(data, indent=2, ensure_ascii=False)
        self.rabbit.send_data_queue(queue, data_json)
        # записываю в БД отчет об отправке
        self.db.response_db(responseid, data, 'ОТВЕТ_ПОСТАВЩИКА', task)
        logging.info('Нажимаю "В дело"')
        self.eosdo.find_element(Selector.send_case).click()
        self.update_list_delivery(task, sender)
        # удаляем задание из списка поиска
        self.tasks.pop(index)
        logging.info(f'Обработка ответа на {reg_number} закончено')
        self.tools.clean_dir(cfg.saved_files)

    def update_list_delivery(self, task: str, organization: str) -> None:
        """
        Запись статуса ответа от Поставщика
        :param task: номер запроса в БД
        :param organization: имя организации от которой получен ответ
        :return:
        """
        # получаем текущий список рассылки
        list_delivery = self.db.get_one(task, 'СПИСОК_РАССЫЛКИ', cfg.table_tasks)
        # записываем статус 'получен'

        organization = self.search_organization(list_delivery, organization)
        if organization:
            list_delivery[organization]['статус'] = 'зарегистрирован'
            no_answer = False
            data_json = json.dumps(list_delivery, indent=2, ensure_ascii=False)
            self.db.do_change_db(task, cfg.table_tasks, {'СПИСОК_РАССЫЛКИ': data_json})

            for organization in list_delivery:
                if list_delivery[organization]['статус'] == 'отправлено' or \
                        list_delivery[organization]['статус'] == 'получен':
                    no_answer = True
            if no_answer is False:
                logging.info(f'По запросу {task} получены ответы от всех предприятий. Записываю в БД статус Закрыт')
                self.db.do_change_db(task, cfg.table_tasks, {'СТАТУС': 'Закрыт'})

        else:
            logging.error(f'В запросе {task} в СПИСКЕ_РАССЫЛКИ не найдено предприятие {organization}')
            raise EXCEPTION_HANDLER.NotFoundOrganization('Не найдена организация')

    def search_organization(self, list_delivery, sender):
        #Первый Алгоритм поиска
        if list_delivery.get(sender, None) is None:
            # разбиваем на список ['АО', 'Пермь']
            word_list = sender.split()
            # выбираем самое длинное имя
            long_text = max(word_list, key=len)
            search_text = re.sub(r'["\'«»]', '', long_text)
            # перебираем по списку организации
            for organization in list_delivery:
                if search_text in organization:
                    logging.info(f'Организация {organization} гайдена')
                    return organization
        # Второй Алгоритм поиска
        symbols = ["\"", "\"", "«", "»", "'", "'", '', '']

        while symbols:
            if list_delivery.get(sender, None) is None:
                # находим символы, которые не участвуют в поиске
                old_symbols = list((Counter(sender) & Counter(symbols)).elements())
                if old_symbols:
                    # исключаем элементы не участувющие в поиске
                    symbols = [symbol for symbol in symbols if symbol not in old_symbols]
                    sender = sender.replace(old_symbols[0], symbols[0], 1).replace(
                        old_symbols[1], symbols[1], 1)
                    continue
                else:
                    logging.error('Организация не найдена')
                    return False
            else:
                logging.info(f'Организация {sender} найдена')
                return sender

