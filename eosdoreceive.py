import logging.config
import logging
import json
import time
import pyperclip
import uuid
from datetime import datetime
from CONFIG import Config as cfg
from pywinauto import keyboard
from pywinauto import Desktop
from selenium.webdriver.common.keys import Keys
import re
import os
from selenium.common.exceptions import TimeoutException
from Lib.b_eosdo import BusinessEosdo
from Lib.b_eosdo import Selector
from Lib.b_outlook import BusinessOutlook
from Lib import EXCEPTION_HANDLER




class EosdoReceive(BusinessEosdo):
    def __init__(self, eosdo_instance=None, conection=None):
        super().__init__()
        self.unknown_document = []
        self.tasks = []
        if eosdo_instance:
            self.__dict__['eosdo'] = eosdo_instance
            self.connection = conection

    @EXCEPTION_HANDLER.exception_decorator
    def start_process(self, tasks, organization):
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
                EXCEPTION_HANDLER.OpenEOSDOError('Ошибка при открытии ЕОСДО')
        try:
            self.main_process(tasks)
        except Exception as err:
            logging.error(f'Ошибка {err}')
            self.reconect_eosdo(organization)
            self.main_process(tasks)

    def main_process(self, tasks):
        #Проверяем наличие пришедших писем
        self.clean_dir(cfg.saved_files)
        self.unknown_document = []
        #нажимаю Задачи/Уведомления
        self.eosdo.find_element("//a[text()='Задачи/Уведомления']").click()
        self.set_filter()
        if self.eosdo.exists_by_xpath(Selector.no_incoming, 5) is False:
            # настройка вывода по 100 документов на станице
            self.eosdo.find_element(Selector.amount_show_files, 5).click()
            self.eosdo.find_element(Selector.hundred, 30).click()
            #Получение числа Входящих документов
            incoming_documents = len(self.eosdo.find_elements(Selector.incoming_row))
            logging.info('Начинаю обработку вх документов в ЕОСДО')
            #Обрабатываем входящие документы
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
                BusinessOutlook().send_mail(cfg.support_email, cfg.robot_name, body)
                logging.info('В поддержку направлено письмо о неизвестном письме в ЕОСДО')
        else:
            logging.info('Входящих писем в ЕОСДО нет')
            logging.info('Обработку вх документов в ЕОСДО закончил')
        # Записываем в базу данных дату проверки документов
        self.db.do_change_db(self.tasks)
        self.exit_eosdo()

    def document_process(self, incoming_documents, tasks, start):
        for document in range(start, incoming_documents + 1):
            reg = ''
            reseived = ''
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
            summary = self.eosdo.find_element(Selector.text_area).text
            #получаю ссылку на документ
            self.eosdo.find_element(Selector.link_project, 10).click()
            link = pyperclip.paste()
            # получаем отправителя данного письма
            try:
                # Отправитель письма
                sender = self.eosdo.find_element(Selector.sender, 3).text
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

    def check(self, tasks, summary, sender, link):
        #сначала поверяем все номера на первой вкладке
        count_page = 1
        while count_page <= 2:
            for index, task in enumerate(tasks):
                reg_number = self.db.get_one(task, 'РЕГ_НОМЕР', 'tuple')[0]
                if count_page == 1:
                    # Ищим рег номер документа в поле краткое содержание документа
                    if reg_number in summary:
                        logging.info(f'{reg_number} найден в поле Краткое содержание')
                        self.process_doc(task, index, sender, link, summary)
                        return True
                    # Ищим рег номер документа в именах прикрепленных файлов
                    elif self.eosdo.exists_by_xpath(f'{Selector.document_info}//label[contains(text(),"{reg_number}")]', 3):
                        logging.info(f'{reg_number} найден в Прикрепленных файлах')
                        self.process_doc(task, index, sender, link, summary)
                        return True
                elif count_page == 2:
                    # Ищим рег номер документа в связанных документах
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
        return False

    def set_filter(self):
        if self.eosdo.exists_by_xpath(Selector.filter_type_doc) is False:
            # очищаю фильтр
            self.eosdo.find_element(Selector.clean_filter, 5).click()
            # выбираю тип документа
            self.eosdo.find_element(Selector.type_doc, 5).click()
            # выбираю входящие
            self.eosdo.find_element(Selector.incoming_doc, 1, 'on').click()
            # применяю
            self.eosdo.find_element(Selector.add_group).click()
            logging.info('Фильтр выставлен')

    def process_doc(self, task, index, sender, link, summary):
        """
        Обработка карточки документа
        :param task: номер запроса в БД
        :param sender: отправитель
        :param reg_number: регистрационный номер документа в ЕОСДО
        :return:
        """
        # сохраняем номер и дату документа
        queue = self.db.get_one(task, 'ЗАПРОС', 'dict')['header']['replayRoutingKey']
        text = self.eosdo.find_element(Selector.reg_number).text
        reg_number = re.findall(r'\d{1,}-\d{1,}\S{0,}\d{1,}', text)[0]
        date = re.findall(r'\d{2}.\d{2}.\d{4}', text)[0]
        self.export_files(cfg.saved_files)

        with open(cfg.response_incoming_mail, 'r', encoding='utf-8') as file:
            data = json.load(file)
        data['header']['id'] = id = str(uuid.uuid4())
        data['header']['sourceId'] = task
        data['header']['date'] = str(datetime.now())
        data['body']['поставщик'] = sender
        data['body']['cсылка'] = link
        data['body']['номер'] = reg_number
        data['body']['дата'] = date
        data['body']['текст сообщения'] = summary
        data['body']['files'] = self.encode_base64(cfg.saved_files)
        data_json = json.dumps(data, indent=2, ensure_ascii=False)
        self.rabbit.send_data_queue(queue, data_json)
        # записываю в БД отчет об отправке
        self.db.response_db(id, data, 'ОТВЕТ_ПОСТАВЩИКА', task)
        self.db.update_list_delivery(task, sender)
        logging.info('Нажимаю "В дело"')
        self.eosdo.find_element(Selector.send_case).click()
        #удаляем задание из списка поиска
        self.tasks.pop(index)
        logging.info(f'Обработка ответа на {reg_number} закончено')
        self.clean_dir(cfg.saved_files)
