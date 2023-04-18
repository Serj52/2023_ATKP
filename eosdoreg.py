
import logging.config
import logging
from datetime import datetime
import time
import pyperclip
import base64
from CONFIG import Config as cfg
from pywinauto import keyboard
from pywinauto import Desktop
import win32com.client as win32
from selenium.webdriver.common.keys import Keys
import json
import re
from collections import Counter
import os
from selenium.common.exceptions import TimeoutException
from b_lib.b_eosdo import BusinessEosdo, Selector
from b_lib.b_post import BusinessPost
import uuid
from eosdomon import EosdoMon, EosdoReceive
from b_lib import EXCEPTION_HANDLER


class EosdoReg(BusinessEosdo):
    def __init__(self):
        super().__init__()
        self.link = None
        self.organization = None
        self.initiator = None
        self.staff_position = None
        self.type_request = None
        self.related_document = None
        self.date_related_document = None
        self.attachments = None
        self.template = None
        self.list_delivery = None
        self.timeout = 60

    @EXCEPTION_HANDLER.exception_decorator
    def start_process(self, tasks: list, organization: str) -> None:
        """
        Процесс обработки запроса
        :return:
        """
        # self.tasks необходим для обработки ошибок
        self.tasks = tasks
        try:
            self.open_eosdo(organization)
        except EXCEPTION_HANDLER.ExctractPWDError as err:
            logging.error(err)
            raise EXCEPTION_HANDLER.ExctractPWDError('Ошибка авторизации')
        except Exception:
            raise EXCEPTION_HANDLER.OpenEOSDOError('Ошибка при открытии ЕОСДО')
        for task in tasks:
            logging.info(f'Создаю документ для запроса: {task}')
            try:
                self.task_process(task, organization)
            except Exception as err:
                logging.info(f'Создание документа по запросу: {task} закончилось неудачно. {err}')
                self.handler_task_error(task, organization)

        # Проверяем есть ли задания на Мониторинг для этой Организации
        query = self.db.get_tasks_monitoring(organization)
        monitoring_tasks = [task[0] for task in query]
        if monitoring_tasks:
            # В данном блоке проверятся и вх.письма в ЕОСДО
            EosdoMon(self.eosdo).start_process(monitoring_tasks, self.organization)
        else:
            # Если на мониторинг ничего нет, проверим вх.письма
            eosdo_incoming_tasks = self.db.get_sending_tasks(organization)
            if eosdo_incoming_tasks:
                logging.info(f'Начинаю мониторинг вх.документов в ЕОСДО для {organization}')
                EosdoReceive(self.eosdo).start_process(eosdo_incoming_tasks, organization)
                self.connection = False
            else:
                self.exit_eosdo()

    @EXCEPTION_HANDLER.exception_decorator
    def task_process(self, task: str, organization: str) -> None:
        self.tools.clean_dir(cfg.saved_files)
        self.task = task
        self.organization = organization
        self.get_parameters(task)
        self.search_template()
        self.create_document(task)
        logging.error(f'!!!--Документ в ЕОСДО для: {task} создан--!!')

    def handler_task_error(self, task: str, organization: str) -> None:
        self.reconect_eosdo(organization)
        try:
            logging.info(f'Начал повторную обработку запроса {task}')
            self.task_process(task, organization)
            logging.info(f'Закончил обработку запроса {task}')
        except Exception as err:
            logging.info(f'Создание документа по запросу {task} закончилось неудачно. {err}')
            self.db.do_change_db(task, cfg.table_tasks, {'ОШИБКИ': 'Не предвиденная ошибка'})
            BusinessPost().send_mail(cfg.support_email, cfg.robot_name, f'Не предвиденная ошибка {err}')
            self.reconect_eosdo(organization)

    def get_parameters(self, task: str) -> None:
        """
        Извлечение параметров из файла PARAMETERS
        :return:
        """
        try:
            parameters = self.db.get_one(task, 'ЗАПРОС', cfg.table_tasks)
            self.organization = parameters['body']['organization']
            self.initiator = parameters['body']['initiator']
            self.staff_position = parameters['body']['staff_position']
            self.type_request = parameters['body']['type_request']
            self.related_document = parameters['body']['number_related_document']
            # self.date_related_document = parameters['body']['date_related_document']
            self.attachments = parameters['body']['files']
            self.template = parameters['body']['template']
            self.queue = parameters['header']['replayRoutingKey']
            self.reseivers_list = parameters['body']['reseivers_list']
        except Exception as err:
            raise EXCEPTION_HANDLER.ExctractError(f'Ошибка извлечения данных из запроса: {err}')

    def search_template(self) -> None:
        """
        Функция поиск шаблона письма в ЕОСДО
        :return:
        """
        template = self.template.split(';')
        logging.info(f'Получен шаблон {template}')
        self.eosdo.find_element(Selector.tab_action).click()
        self.eosdo.find_element(Selector.fild_create_doc).click()
        try:
            for temp in template:
                self.eosdo.find_element(f'//a[contains(text(),"{temp}")]', self.timeout).click()
            self.eosdo.find_element(Selector.button_select, self.timeout).click()
            time.sleep(1)
            # Если шаблон не добавился вызываем исключение
            if self.eosdo.exists_by_xpath("//div[contains(text(), 'Шаблоны')]") is True:
                raise TimeoutException
            else:
                logging.info('Шаблон найден')
                self.template = template
        except TimeoutException:
            logging.error('Шаблон не найден')
            self.eosdo.find_element("//button[contains(text(), 'Отменить')]", self.timeout).click()
            raise EXCEPTION_HANDLER.TemplateError(f'Шаблон {template} не найден')

    def create_document(self, task: str) -> None:
        """
        Главный процесс по созданию проекта документа в ЕОСДО
        :return:
        """
        if self.type_request == 'дозапрос':
            # В дозапросе сначала заполняется третья вкладка
            self.fill_third_tab()
            self.fill_first_tab()
        else:
            self.fill_first_tab()
        self.fill_second_tab()
        self.save_project(task)

    def fill_first_tab(self) -> None:
        """
        Функция заполнения вкладки Основные реквизиты
        :return:
        """
        self.fill_fields()
        self.add_file()
        self.mark_as_main()
        self.insert_amount_page()

    def fill_fields(self) -> None:
        """
        Заполнение полей во вкладке Основные реквизиты
        :return:
        """
        # Заполнить поле краткое содержание
        self.eosdo.find_element(Selector.contents, self.timeout).send_keys('Коммерческое предложение')
        logging.info('Поле краткое содержание заполнено')
        # Заполнить поле Работник
        self.eosdo.find_element(Selector.body).send_keys(Keys.PAGE_DOWN)
        self.eosdo.find_element(Selector.employee_page1).click()
        self.search_employee()
        # Заполнить поле Способ Доставки
        self.search_organization()
        logging.info('Вкладка Основные реквизиты заполнена')

    def search_organization(self) -> None:
        """
        Поиск организации на вкладке Основные реквизиты
        :return:
        """
        type_delivery = []  # список для хранения типов доставки для данного документа
        new_list = {}
        for organization in self.reseivers_list:
            type_organization = self.reseivers_list[organization]['type']
            self.reseivers_list[organization]['статус'] = ''
            try:
                if type_organization.lower() == 'отраслевая':
                    self.eosdo.find_element(Selector.organization_inside).click()
                    type_delivery.append('еосдо')
                    symbols = ["\"", "\"", "«", "»", "'", "'", '', '']
                    curr_name = organization
                    while symbols:
                        self.eosdo.find_element(Selector.fild_search, self.timeout).send_keys(organization)
                        self.eosdo.find_element(Selector.button_search).click()
                        #Если есть окно загрузки ждем
                        self.eosdo.wait_loading_window(Selector.block, self.timeout)
                        if self.eosdo.exists_by_xpath(fr"//a[text()='{organization}']", 1):
                            self.eosdo.find_element(fr"//a[text()='{organization}']").click()
                            # перезаписывем наименование организации, т.к. найденное наименование может отличаться от того,
                            # что  получили в ЗАпросе
                            new_list[organization] = self.reseivers_list[curr_name]
                            break

                        else:
                            # очистить поиск
                            self.eosdo.find_element('//span[@class="fa fa-times"]').click()
                            # находим символы, которые не участвуют в поиске
                            old_symbols = list((Counter(organization) & Counter(symbols)).elements())
                            if old_symbols:
                                # исключаем элементы не участувющие в поиске
                                symbols = [symbol for symbol in symbols if symbol not in old_symbols]
                                organization = organization.replace(old_symbols[0], symbols[0], 1).replace(
                                    old_symbols[1], symbols[1], 1)
                            else:
                                raise TimeoutException

                elif type_organization.lower() == 'не отраслевая':
                    new_list[organization] = self.reseivers_list[organization]
                    if self.eosdo.exists_by_xpath('//td[text()="По списку рассылки"]', 1):
                        continue
                    else:
                        self.eosdo.find_element(Selector.organization_outside).click()
                        self.eosdo.find_element(Selector.fild_search, self.timeout).send_keys('по списку рассылки')
                        self.eosdo.find_element(Selector.button_search).click()
                        self.eosdo.find_element(fr"//a[contains(text(),'По списку рассылки')]", self.timeout).click()
                        type_delivery.append('электронная_почта')
                else:
                    logging.error('Некорректно указан тип организации в запросе')
                    raise TimeoutException
                self.eosdo.find_element(Selector.button_add, self.timeout).click()
            except TimeoutException:
                logging.error(f'Организация {organization} не добавлена')
                # если мы зашли в окно справочника
                if self.eosdo.exists_by_xpath("//div[contains(text(), 'Исходящий документ')]") is False:
                    self.eosdo.find_element(Selector.button_cansel, timeout=self.timeout).click()
                time.sleep(1)
                if self.eosdo.exists_by_xpath(Selector.block, 1):
                    keyboard.send_keys("{ESC}")
                self.send_task_employee()
                raise EXCEPTION_HANDLER.NotFoundOrganization('Не найдена организация')

            if type_organization.lower() == 'отрослевая':
                self.apply_delivery(organization, 'ЕОСДО')
            elif type_organization.lower() == 'не отраслевая':
                self.apply_delivery('По списку рассылки', 'Электронная почта')

            # Если доставка не применилась
            if self.eosdo.exists_by_xpath(Selector.delivery_error, 5):
                logging.error(f'Указанный способ доставки не был добавлен для {organization}')
                # нажимаем на способ доставки
                self.apply_delivery(organization, 'Электронная почта')
                # Удаляем неприменившуюся доставку из списка
                type_delivery.pop(len(type_delivery) - 1)
                # Добавляем способ доставки электронная_почта
                type_delivery.append('электронная_почта')
        # определяем тип доставки для документа
        if 'электронная_почта' in type_delivery and 'еосдо' in type_delivery:
            self.type_delivery = 'смешанный'
        elif 'электронная_почта' in type_delivery:
            self.type_delivery = 'электронная почта'
        elif 'еосдо' in type_delivery:
            self.type_delivery = 'еосдо'
        self.reseivers_list = new_list
        self.list_delivery = json.dumps(self.reseivers_list, indent=4, ensure_ascii=False)

    def apply_delivery(self, organization: str, type_delivery: str) -> None:
        """
        Выбрать способ доставки для организации
        :param organization: название организации из запроса
        :param type_delivery: способ доставки, указанный в запросе
        :return:
        """
        # нажимаем на способ доставки
        self.eosdo.find_element(Selector.button_delivery, self.timeout).click()
        self.eosdo.find_element(f'//a[contains(text(),"{type_delivery}")]', timeout=self.timeout).click()
        self.eosdo.find_element(Selector.button_add, self.timeout).click()
        logging.info('Организация добавлена')
        # Применить Способ Доставки
        self.eosdo.find_element(f"//td[contains(text(),'{organization}')]", self.timeout).click()
        self.eosdo.find_element(Selector.apply_delivery, self.timeout).click()
        element = self.eosdo.find_element(Selector.type_delivery, self.timeout)
        self.clean_fild(element)
        logging.info('Применили доставку')

    def search_employee(self) -> None:
        """
        Поиск ФИО. Заполнение поля Работник
        :return:
        """
        try:
            logging.info('Добавляю соисполнителя')
            self.eosdo.find_element(
                Selector.fild_search, self.timeout).send_keys(self.initiator)
            self.eosdo.find_element(Selector.button_search).click()
            self.eosdo.wait_loading_window(Selector.block, self.timeout)
            if self.eosdo.exists_by_xpath(f"//*[@id='body.treeObjects']//a[contains(text(),'{self.organization}')]", 2):
                organizations = len(self.eosdo.find_elements("//*[@id='body.treeObjects']/ul/li/ul/li", self.timeout))
                # перебираем дерево организаций
                for index in range(1, organizations + 1):
                    self.eosdo.scroll_to_element(fr"//*[@id='body.treeObjects']/ul/li/ul/li[{index}]")
                    # если существует организация исполнителя
                    if self.eosdo.exists_by_xpath(
                            fr"//*[@id='body.treeObjects']/ul/li/ul/li[{index}]//a[text()='{self.organization}']"):
                        xpath = fr'//*[@id="body.treeObjects"]/ul/li/ul/li[{index}]'
                        # в цикле наращиваем xpath, ищем должность
                        while True:
                            tail = r'/ul/li'
                            xpath = xpath + tail
                            # если в найденых результатах существует xpath
                            if self.eosdo.exists_by_xpath(xpath):
                                self.eosdo.scroll_to_element(xpath)
                                selector = fr'{xpath}/a[text()="{self.staff_position}"]'
                                # если находим нужную должность, добавляем сотрудника
                                if self.eosdo.exists_by_xpath(selector):
                                    xpath = xpath + tail
                                    self.eosdo.scroll_to_element(selector)
                                    self.eosdo.find_element(f"{xpath}/a[text()='{self.initiator}']").click()
                                    self.eosdo.find_element(Selector.button_add, self.timeout).click()
                                    logging.info('Соисполнитель добавлен')
                                    return
                                else:
                                    continue
                            else:
                                logging.error(f'Ошибка при заполнении поля "Работник". Не найден {self.initiator}')
                                self.error_worker()
                                raise EXCEPTION_HANDLER.NotFoundEmployee('Не найдено ФИО')
            else:
                logging.error(f'Не найден {self.initiator}')
                self.error_worker()
                raise EXCEPTION_HANDLER.NotFoundEmployee('Не найдено ФИО')
        except TimeoutException:
            logging.error(f'Не найден {self.initiator}')
            self.error_worker()
            raise EXCEPTION_HANDLER.NotFoundEmployee('Не найдено ФИО')

    def error_worker(self) -> None:
        """
        Выход из карточки документа в случае не найденных данных
        :return:
        """
        logging.info('Ошибка. Выхожу из карточки документа')
        if self.eosdo.exists_by_xpath(Selector.block, 1):
            time.sleep(5)
            keyboard.send_keys("{ESC}")
        # проверка находимся ли мы в карточке или внутри справочника
        if self.eosdo.exists_by_xpath("//div[contains(text(), 'Исходящий документ')]") is False:
            self.eosdo.find_element(Selector.button_cansel, self.timeout).click()
        self.eosdo.find_element(Selector.button_cansel, self.timeout).click()
        self.eosdo.find_element(Selector.button_ok, self.timeout).click()

    def add_file(self, max_tries=130) -> None:
        """
        Функция загрузки документов в карточку проекта
        :param max_tries: число попыток открыть Проводник
        :return:
        """
        try:
            self.body_task = self.db.get_one(self.task, 'ЗАПРОС', cfg.table_tasks)
            # получаем список файлов из тела запроса
            files_task = self.body_task['body']["files"]
            files_list = []
            for file in files_task:
                files_list.append(file['file_name'])
                with open(os.path.join(cfg.saved_files, file['file_name']), "wb") as newfile:
                    # декодируем файлы из base64 и сохраняем в Saved_files
                    newfile.write(base64.b64decode(file["file"]))
            # перезаписываем поле files, что бы не хранить двоичные данные в БД
            self.body_task['body']["files"] = files_list
            self.body_task = json.dumps(self.body_task, indent=2, ensure_ascii=False)
            logging.info(f'Открываю документы ')
            self.eosdo.find_element(Selector.button_add_file, self.timeout)
            while max_tries > 0:
                self.eosdo.find_element(Selector.button_add_file, self.timeout).click()
                if self.eosdo.exists_by_xpath(Selector.button_close, 2):
                    self.eosdo.find_element(Selector.button_close).click()
                    max_tries -= 1
                else:
                    logging.info('Проводник открылся')
                    win = Desktop(backend="uia").window(title_re='Open')
                    win.wait('ready', timeout=self.timeout, retry_interval=1)
                    win.set_focus()
                    win['File Name:'].click_input()
                    keyboard.send_keys(cfg.saved_files, with_spaces=True)
                    keyboard.send_keys('{ENTER}')
                    for i in win.child_window(title="Items View", control_type="List").wrapper_object():
                        i.click_input(button='left', pressed='control')  # с нажатым Ctrl
                        time.sleep(1)
                    win.child_window(title="Open", auto_id="1", control_type="Button").click_input()
                    return
        except Exception as err:
            logging.error(err)
            self.send_task_employee()
            raise EXCEPTION_HANDLER.AddedFileError('Ошибка при загрузке докуметов в ЕОСДО')

    def mark_as_main(self) -> None:
        """
        Сделать загруженный документ основным
        :return:
        """
        try:
            logging.info(f'Устанавливаю флаг "Основной"')
            elements = self.eosdo.find_elements(Selector.amount_added_files_close, self.timeout)
            for element in elements:
                if 'запрос' in element.text.lower():
                    element.click()
                    self.eosdo.find_element(Selector.button_main).click()
                    logging.info(f'Флаг установлен')
                    return
            logging.error('Ошибка при устанавке флага "Основной" Не найден файл Запрос')
            raise
        except Exception as err:
            logging.error(f'Ошибка при установке флага "Основной" {err}')
            self.send_task_employee()
            raise EXCEPTION_HANDLER.AddedFileError('Проверьте формат файла Запрос')

    def insert_amount_page(self) -> None:
        """
        Подсчет кол-ва страниц в основном документе
        :return:
        """
        try:
            time.sleep(1)
            logging.info(f'Указываю число страниц')
            for file in os.listdir(cfg.saved_files):
                if 'запрос' in file.lower():
                    word = win32.gencache.EnsureDispatch('Word.Application')
                    path_file = os.path.join(cfg.saved_files, file)
                    doc = word.Documents.Open(path_file)
                    amount_page = doc.ComputeStatistics(2)
                    doc.Close(False)
                    word.Application.Quit()
                    logging.info(f'Число страниц в документе {amount_page}')
                    self.eosdo.find_element(Selector.page_count).send_keys(amount_page)
                    return
            logging.error('Ошибка при указании числа страниц. Не найден файл Запрос')
            raise
        except Exception as err:
            logging.error(f'Ошибка при подсчете числа страниц {err}')
            raise

    def fill_second_tab(self) -> None:
        """
        Заполнение вкладки Согласование и Подписание
        :return:
        """
        # Заполнить поле Работник на вкладке Согласование и Подписание
        self.eosdo.find_element(Selector.tab_approval).send_keys(Keys.ENTER)
        # self.eosdo.find_element(Selector.employee_page2, 30).click()
        # self.search_employee()
        # выставить дни согласования
        # self.set_approval_days()
        # Завершить
        time.sleep(2)
        self.eosdo.find_element(Selector.senddraft, self.timeout).click()
        logging.info('Вторая вкладка заполнена')

    def fill_third_tab(self) -> None:
        """
        Заполнение вкладки Связанные документы
        :return:
        """
        logging.info('Заполняю вкладку Связанные документы')
        self.eosdo.find_element(Selector.tab_related_doc).send_keys(Keys.ENTER)
        self.eosdo.find_element(Selector.add_related_doc, self.timeout).click()
        # Очищаем дату регистрации
        element = self.eosdo.find_element(Selector.date_reg, self.timeout)
        self.clean_fild(element)
        # self.eosdo.find_element(Selector.date_reg, 20).send_keys(self.date_related_document)
        self.eosdo.find_element(Selector.number_related_doc).send_keys(self.related_document)
        self.eosdo.find_element(Selector.button_search_doc).click()
        logging.info(f'Ищу {self.related_document}')
        try:
            self.eosdo.find_element(fr'//span[contains(text(),"{self.related_document}")]', self.timeout).click()
        except TimeoutException:
            self.error_worker()
            logging.error(f'{self.related_document} не найден. При заполнении вкладки Связанные документы')
            raise EXCEPTION_HANDLER.NotFoundDocument(f'Не найден связанный документ')

        self.eosdo.find_element(Selector.button_select, self.timeout).click()
        self.eosdo.find_element(Selector.tab_main, self.timeout).send_keys(Keys.ENTER)
        logging.info('Третья вкладка заполнена')

    def set_approval_days(self) -> None:
        """
        Устанавливаю число дней согласования документа
        :return:
        """
        queue_approval = len(self.eosdo.find_elements('//table[@id="queues"]//tr'))
        for index in range(1, queue_approval + 1):
            # находим нужную строку
            if self.eosdo.exists_by_xpath(f'//table[@id="queues"]//tr[{index}]//td[@colspan="9"]'):
                # получаем количество дней на согласование документа
                day = self.eosdo.find_element(
                    f'//table[@id="queues"]//tr[{index}]//td[@colspan="9"]{Selector.queue_sogl}').text
                if day != "0":
                    continue
                else:
                    # кликаем по чекбоксу
                    self.eosdo.find_element(
                        f'//table[@id="queues"]//tr[{index}]//td[@colspan="9"]{Selector.queue_sogl}').click()
                    # выбираем 3
                    self.eosdo.find_element(
                        f'//table[@id="queues"]//tr[{index}]//td[@colspan="9"][1]//ul/li[text()="3"]').click()
                    time.sleep(1)
                    queue_name = self.eosdo.find_element(
                        f'//table[@id="queues"]//tr[{index}]//td[@colspan="9"]{Selector.queue_name}').text
                    logging.info(f'Установлено 3 дня на согласования для очереди {queue_name}')

    def save_project(self, task: str) -> None:
        """
        Сохранение номера проекта и отправка данных следующему роботу
        В случае возникновения ошибки робот не перезапустит данное задание заново воизбежании повторного
        создания документа
        :return:
        """
        project = None
        date = None
        try:
            if self.eosdo.exists_by_xpath(r'//h4[text()="Проект документа создан"]', self.timeout):
                project_info = self.eosdo.find_element(
                    r'//h4[text()="Проект документа создан"]//ancestor::div[@class="modal-header navbar-inverse"]//following::div',
                    30).text
                clean_text = project_info.replace("\n", "")
                project = re.findall(r'\d{1,}\W\d{1,}-ПРОЕКТ', clean_text)[0]
                date = re.findall(r'\d\d.\d\d.\d\d\d\d', clean_text)[0]
                self.eosdo.find_element(r'//button[contains(text(),"Завершить")]').click()
                # Повторно открываем карточку
                self.eosdo.find_element(Selector.search_doc).click()
                # Очищаем дату регистрации
                element = self.eosdo.find_element(Selector.date_reg, self.timeout)
                self.clean_fild(element)
                time.sleep(1)
                # Вбиваем дату проекта
                self.eosdo.find_element(Selector.date_project, self.timeout).send_keys(date)
                # Вбиваем проект
                self.eosdo.find_element(Selector.project_number).send_keys(project)
                # Нажимаем поиск
                self.eosdo.find_element(Selector.button_search_doc).click()
                # перехожу в проект
                time.sleep(1)
                self.eosdo.double_click(fr'//span[text()="{project}"]', self.timeout)
                # копирую ссылку
                self.eosdo.find_element(Selector.link_project, self.timeout).click()
                version = self.eosdo.find_element(Selector.version_doc, self.timeout).text.strip()
                status = self.eosdo.find_element(Selector.status_doc, self.timeout).text.strip()
                link_project = pyperclip.paste()
                list_sogl = self.create_list_sogl(project=project, version=version, status=status)
                # выхожу из карточки
                self.eosdo.find_element(Selector.button_cansel).click()
                self.eosdo.find_element(Selector.button_cansel).click()
                # записывваем данные в таблицу eosdo_427
                self.db.add_project_db(
                    task,
                    project,
                    datetime.strptime(date, '%d.%m.%Y'),
                    list_sogl,
                    link_project,
                    status
                )
                # обновляем данные в таблицt tasks_427
                self.db.do_change_db(
                    task,
                    cfg.table_tasks,
                    {
                        'СТАТУС': 'Мониторинг',
                        'СПОСОБ_ОТПРАВКИ': self.type_delivery,
                        'СПИСОК_РАССЫЛКИ': self.list_delivery,
                        'ЗАПРОС': self.body_task
                    }
                )
                logging.info(f'Проект {project} отправлен на согласование в ЕОСДО')
                # отправка в шину сообщения о создании проекта
                with open(cfg.response_tkp_done, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                data['header']['requestID'] = responseid = str(uuid.uuid4())
                data['header']['sourceId'] = task
                data['header']['date'] = str(datetime.now())
                data['body']['проект'] = project
                data['body']['ссылка'] = link_project
                data_json = json.dumps(data, indent=2, ensure_ascii=False)
                self.rabbit.send_data_queue(self.queue, data_json)
                # записываю в БД отчет об отправке
                self.db.response_db(responseid, data, 'ПРОЕКТ_СОЗДАН', task)
            else:
                logging.error('Номер и дата проекта не сохранены')
        except Exception as err:
            logging.error(f'Ошибка при сохранении проекта {project} от {date}. '
                          f'Проверьте последние созданные документы: {err}')
            raise EXCEPTION_HANDLER.SaveProjectError('Ошибка при сохранении проекта')

    def send_task_employee(self):
        """
        Отправка задания соисполнителю для проверки ошибок
        """
        self.eosdo.find_element(Selector.button_save, self.timeout).click()
        self.eosdo.find_element(Selector.button_ok, self.timeout).click()
        if self.eosdo.exists_by_xpath("//div[text()='Отправка задач на соисполнителей']", self.timeout):
            time.sleep(1)
            self.eosdo.find_element("//button[@id='.yes']").click()
            logging.info('Задача отправлена соисполнителю')
        else:
            logging.error('Ошибка при отправке задания СОИСПОЛНИТЕЛЮ')
