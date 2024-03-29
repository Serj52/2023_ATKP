import logging.config
import logging
import time
import json
from CONFIG import Config as cfg
from pywinauto import Desktop
from selenium.webdriver.common.keys import Keys
import os
from b_lib import DATABASE, b_excel, EOSDO, RABBIT, actionfiles
import shutil
from dataclasses import dataclass
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pywinauto import keyboard
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from b_lib.EXCEPTION_HANDLER import ExctractPWDError



@dataclass
class Selector:
    # Селекторы входа в ЕОСДО
    username = '//input[@id=".txtUsername"]'
    pwd = '//input[@id=".txtUserPassword"]'
    button_entrance = '//button[contains(text(),"Войти")]'
    entrance_error = '//p[contains(text(),"Неправильный логин или пароль")]'
    # Создание документа в ЕОСДО
    tab_action = '//button[contains(text(),"Действия")]'
    fild_create_doc = '//a[contains(text(),"Создать проект документа")]'
    button_select = '//button[contains(text(),"Выбрать")]'
    contents = '//textarea[@id="OutgoingDocumentPage1_contents.taContent"]'
    body = '//body'
    employee_page1 = '//button[@id="OutgoingDocumentPage1_contents.lvCoPerformers.clObjectToAdd_Btn"]'
    employee_page2 = '//button[@id="DocumentPage2_contents.cmpDocumentApproval.ApproversListView.clObjectToAdd_Btn"]'
    fild_search = '//input[@id="body.txtSearchText"]'
    button_search = "//button[@title='Поиск']"
    button_add = "//button[contains(text(),'Добавить')]"
    organization_inside = '//button[@id="OutgoingDocumentPage1_contents.lvCorrespondents.clObjectToAddOrg_Btn"]'
    organization_outside = '//button[@id="OutgoingDocumentPage1_contents.lvCorrespondents.clObjectToAdd_Btn"]'
    button_cansel = "//button[@id='.btnCancel']"
    button_save = "//button[@id='.btnSave']"
    button_ok = "//button[@id='dialog-btn-ok']"
    button_clean = '//button[contains(text(),"Очистить")]'
    delivery_error = '//p[contains(text(),"Указанный способ доставки не был добавлен")]'
    button_delivery = '//button[@id="OutgoingDocumentPage1_contents.lvCorrespondents.clDeliveryType_Btn"]'
    apply_delivery = '//button[@id="OutgoingDocumentPage1_contents.lvCorrespondents.' \
                     'OutDocCorrespApplyDeliveryTypeListViewAction"]'
    type_delivery = '//input[@id="OutgoingDocumentPage1_contents.lvCorrespondents.clDeliveryType"]'
    button_add_file = '//button[@id="component6-AddDocumentAttachmentListViewAction"]'
    button_close = '//div[@id="usr34865"]//button[contains(text(),"Закрыть")]'
    amount_added_files_close = '//table[@id="component6-files"]//div[@class="document-info"]'
    amount_added_files_income = '//table[@id="component9-files"]//div[@class="document-info"]'
    button_main = '//button[@title="Основной"]'
    tab_approval = '//a[text()="Согласование и подписание"]'
    tab_main = '//a[text()="Основные реквизиты"]'
    tab_related_doc = '//a[text()="Связанные документы"]'
    page_count = '//input[@id="OutgoingDocumentPage1_contents.txtDocumentPagesCount"]'
    search_doc = '//button[@class="fa fa-12x fa-search btn btn-primary"]'
    date_reg = '//input[@id="SearchPage1_contents.cmpDocumentSearchComponent.diDocumentRegDate"]'
    date_project = '//input[@id="SearchPage1_contents.cmpDocumentSearchComponent.diDocumentProjectCreateDateRange"]'
    project_number = '//input[@id="SearchPage1_contents.cmpDocumentSearchComponent.txtDraftNumber"]'
    button_search_doc = '//button[contains(text(),"Поиск")]'
    not_found_project = '//td[text()="Не найдены документы, удовлетворяющие заданным параметрам"]'
    status_doc = '//div[@class="doc-status inline-block pd-r-15"]//span'
    version_doc = '//div[@class="doc-version inline-block pd-r-15"]//span'
    add_related_doc = '//button[@id="DocumentPage6_contents.lvRelatedDocuments.CreateRelationListViewAction"]'
    number_related_doc = '//input[@id="SearchPage1_contents.cmpDocumentSearchComponent.txtDocumentRegNumber"]'
    approve_rows = '//tr[contains(@class,"expanded")]'
    checkbox = '//div[@id="dialog_body"]//th//input[contains(@id,checkbox)]'
    amount_files_checkbox = r'//div[@id="dialog_body"]//div[@class="dataTables_info"]'
    reg_number = '//div[@class="doc-num-title"]'
    xpath_reg_number = '//td[@class=" doc_reg_num_date"]//span[@class="hrow-hrow-h3"]'
    received = '//td[@class=" task_date"]'
    dialog_body = '//div[@id="dialog_body"]'
    tbody = '//div[@id="dialog_body"]//tbody'
    senddraft = '//button[@id=".btnSendDraft"]'
    type_doc = '//input[@id="Inbox.cmpFilter.ddlDocTypePluralmock_input"]'
    incoming_doc = '//li[contains(text(), "Входящий документ")]'
    add_group = '//button[@id="add-group" and contains(text(), "Применить")]'
    clean_filter = '//button[@id="add-group" and contains(text(), "Очистить")]'
    queue_sogl = '//div[@class="form-control slct dropdown-toggle prevent-user-select"]'
    queue_name = '//div[@class="form-control slct dropdown-toggle prevent-user-select disabled"]'
    filter_type_doc = '//input[@id="Inbox.cmpFilter.ddlDocTypePluralmock_input" and contains(@value, "Входящий документ")]'
    amount_show_files = '//div[@class="form-control slct pagin dropdown-toggle"]'
    hundred = '//ul[@class="dropdown-menu dropdown-menu-drop"]//li[text()="100"]'
    incoming_row = '//table[@id="InboxDataTable"]//tbody/tr'
    text_area = '//textarea[@id="IncomingDocumentPage1_contents.taContent"]'
    sender = '//*[@id="component3"]/tbody//td[3]'
    document_info = '//div[@class="document-info"]'
    send_case = '//button[@id=".btnSendDocumentToCase"]'
    all_in_checkbox = '//div[@id="dialog_body"]//th//input[contains(@id,checkbox)]'
    senddraftsignin = '//button[@id=".btnRevokeSendDraftSignInEOSDO"]'
    doc_page = '//a[@name="OutgoingDocumentPage1"]'
    block = '//div[@class="blockUI blockOverlay"]'
    no_incoming = "//*[@id='InboxDataTable']/tbody/tr/td[contains(text(), 'отсутствуют данные')]"
    link_project = "//span[@class='fa fa-external-link-square color-white']"
    docs = '//a[text()="Документы"]'
    link_created_by_me = '//a[text()="Созданные мной"]'
    row_my_doc_first = '//table[@id="MyDocumentsDataTable"]/tbody/tr[1]'
    filter_apply = '//button[@id="add-group" and contains(text(), "Фильтр применен")]'
    type_tasks = '//input[@id="Inbox.cmpFilter.ddlItemNamePluralmock_input"]'
    consideration = '//li[text()="На рассмотрение"]'
    button_export_queue = '//div[@id="dialog_body"]//button[@title="Экспорт"]'
    button_export_close = '//button[@id="component6-ExportFileListViewAction"]'
    button_export_income = '//button[@id="component9-ExportFileListViewAction"]'
    select_all_close = '//input[@id="component6-files-checkbox-select-all"]'
    select_all_income = '//input[@id="component9-files-checkbox-select-all"]'
    el_document = '//div[@class="doc-task pull-right" and contains(text(), "Электронный")]'


class BusinessEosdo:
    def __init__(self):
        self.eosdo = EOSDO.Eosdo()
        self.db = DATABASE.DateBase()
        self.rabbit = RABBIT.Rabbit()
        self.connection = False
        self.tools = actionfiles.ActionFiles
        self.excel = b_excel.Excel()
        self.task = None
        self.status = None
        self.queue = None

    def open_eosdo(self, organization: str, max_tries=3) -> None:
        while max_tries > 0:
            try:
                self.entry_eosdo(organization)
                self.infowindows_checkANDclose()
                self.connection = True
                return
            except ExctractPWDError:
                raise ExctractPWDError('Ошибка авторизации')
            except Exception as err:
                max_tries -= 1
                logging.error(f'Ошибка при открытии ЕОСДО {err}')
                self.eosdo.close_site()
                if max_tries == 1:
                    logging.error(f'Пробую повторно открыть ЕОСДО через 10 мин')
                    time.sleep(600)
                elif max_tries > 1:
                    logging.error(f'Пробую повторно открыть ЕОСДО через 1 мин')
                    time.sleep(60)
        raise

    def entry_eosdo(self, organization: str, max_tries=10) -> None:
        """
        Функция открытия ЕОСДО
        :return:
        """
        credential = self.excel.get_pwd(organization, cfg.credentials_file)
        self.eosdo.open_site(site_url=cfg.url,
                             driver_path=cfg.chrome_driver,
                             browser_path=cfg.chrome_path
                             )
        self.eosdo.find_element(Selector.username).send_keys(credential['username'])
        self.eosdo.find_element(Selector.pwd).send_keys(credential['pwd'])
        self.eosdo.find_element(Selector.button_entrance).click()

        if self.eosdo.exists_by_xpath(Selector.entrance_error):
            logging.error('Ошибка. Неправильный логин или пароль')
            self.eosdo.close_site()
            raise ExctractPWDError('Ошибка авторизации')
        while 'ЕОСДО | Главная' not in self.eosdo.driver.title:
            time.sleep(1)
            logging.error('Исчерпан лимит ожидания загрузки страницы, нет возможности открыть "ЕОСДО | Главная"')
            if max_tries == 0:
                raise
            else:
                time.sleep(5)
            max_tries -= 1

    # Проверка на наличие информационных окон и если обнаружены - их закрытие.
    @staticmethod
    def infowindows_checkANDclose(java=True) -> None:
        """
        Проверка на наличие инфо окон и их закрытие.\n
        Аргументы:\n
        * java - Запускаем ли java приложение? По умолч.True
        """
        logging.info("Проверяю наличие / закрываю инфо окна...")

        # Окно 'Open EosdoJwsLauncher?'
        if Desktop(backend="uia").window(title_re='^Open.*').exists(50):
            logging.info("Обнаружено окно 'Open EosdoJwsLauncher?'! Закрываю это окно...")
            element = Desktop(backend="uia").window(title_re='^Open.*')

            def worker():
                element.wait("exists visible enabled ready active", timeout=10)
                element['Open EosdoJwsLauncher'].click_input(use_log=False) if java \
                    else element['Cancel'].click_input(use_log=False)
                time.sleep(5)

            # Выполняю проверку закрылось ли инфо окно, если нет - снова пробую закрыть
            while element.exists(5):
                worker()
            logging.info("Окно 'Open EosdoJwsLauncher?' успешно закрыто.")

        # Окно 'Security Warning' (Запуск java приложения)
        if java and Desktop(backend="uia").window(title='Security Information').exists(15):
            logging.info("Обнаружено java окно 'Security Warning'! Закрываю это окно...")
            element = Desktop(backend="uia").window(title='Security Information')
            element.wait("exists visible enabled ready", timeout=10)
            element.set_focus()
            keyboard.send_keys('{ENTER}')
            logging.info("Java окно 'Security Warning' успешно закрыто.")

        # Особенности ЕОСДО для полноценной дальнейшей работы...
        if java and Desktop(backend="uia").window(title_re='^Starting.*').exists(10):
            logging.info("Окно java application появилось")
            logging.info("Ожидаю инициализацию java application...")
            count = 120
            while count > 0:
                if Desktop(backend="uia").window(title_re='^Starting.*').exists():
                    count -= 1
                    time.sleep(1)
                else:
                    logging.info("Ожидание инициализации java application завершено.")
                    return
        logging.info("java application не открылось")

    def reconect_eosdo(self, organization: str):
        # В случае ошибки повторно открываем ЕОСДО
        self.eosdo.close_site()
        logging.info('Подключусь к ЕОСДО повторно через 1 мин')
        time.sleep(60)
        self.open_eosdo(organization)

    def export_files(self, path: str, amount_files: int = None, max_tries=120) -> None:
        """
        Экспорт файлов в папку
        :param path:
        :param amount_files: число файлов для загрузки
        :param max_tries: число попыток
        """
        logging.info('Экспортирую файлы')
        element = 'webelement'
        if self.__module__ == 'eosdomon':
            if self.status == "Доработка" or self.status == "Подтверждение отправки на подписание в ЕОСДО":
                element = self.eosdo.find_element(Selector.button_export_queue)
            elif self.status == "Закрыт":
                # выделяем все файлы
                self.eosdo.find_element(Selector.select_all_close, 10).click()
                element = self.eosdo.find_element(Selector.button_export_close)
                if self.eosdo.exists_by_xpath(Selector.el_document, 10):
                    amount_files += 1
                # TODO еще раз обсудить момент, когда скачиваются два файла

        elif self.__module__ == 'eosdoreceive':
            # экспортируем файлы в папку
            self.eosdo.find_element(Selector.select_all_income, 10).click()  # выделяем все файлы
            element = self.eosdo.find_element(Selector.button_export_income)
            # если тип документа не Бумажный, то amount_files инкреминируемм т.к. кроме самого файла сохраняется еще файл с ЭП
            # if self.eosdo.exists_by_xpath('//div[@class="doc-task pull-right" and contains(text(), "Электронный")]',
            #                               10):
            #     amount_files += 1
            if self.eosdo.exists_by_xpath("//label[contains(text(), 'doc')]") is False:
                amount_files += 1

        while max_tries > 0:
            element.click()  # открываем проводник
            if self.eosdo.exists_by_xpath(Selector.button_close, 2):
                self.eosdo.find_element(Selector.button_close).click()
                time.sleep(5)
                max_tries -= 1
            else:
                win = Desktop(backend="uia").window(best_match='Select FolderDialog')
                try:
                    win.wait('ready', timeout=10, retry_interval=1)
                    win.set_focus()
                except TimeoutError:
                    max_tries -= 1
                    logging.info('Проводник не открылся. Нажимаю Esc')
                    keyboard.send_keys("{ESC}")
                    continue
                win.click_input()
                logging.info('Проводник открылся')
                win.child_window(class_name='Edit').click_input()
                os.makedirs(path, exist_ok=True)
                # Экранирование для случаем Мальцева (норма)
                if '(' in path and ')' in path:
                    keyboard.send_keys(path.replace("(", "{(}").replace(")", "{)}"), with_spaces=True)
                else:
                    keyboard.send_keys(path, with_spaces=True)
                keyboard.send_keys('{ENTER}')
                win['Select Folder'].click_input()
                # проверяю число сохраненных файлов
                logging.info('Проверяю число сохраненных файлов')
                max_tries = 60
                while max_tries > 0:
                    count_files = len([file for file in os.listdir(path)])
                    if count_files == amount_files:
                        logging.info(f'Число файлов в папке {count_files}')
                        logging.info('Файлы сохранены')
                        self.close_exporter()
                        return
                    else:
                        if max_tries == 0:
                            logging.error(
                                f'Время ожидания загрузки фалов истекло. '
                                f'Число файлов в папке {count_files} ожидалось {amount_files}')
                            raise
                        else:
                            max_tries -= 1
                            logging.info(
                                f'Ожидаю файлы. Число файлов в папке {count_files} ожидалось {amount_files}')
                            time.sleep(1)
                            continue
        else:
            logging.info('Проводник не открылся')
            raise

    def create_list_sogl(self, project: str, version: str, status: str) -> json:
        """
        Создание листа согласования
        :return:
        """
        self.eosdo.find_element(Selector.tab_approval).click()
        logging.info('Создаю Лист согласования')
        sogl_list = {}
        queue = ''
        sogl_list['проект'] = project
        sogl_list['версия'] = version
        sogl_list['статус'] = status
        sogl_list['лист_согласования'] = {}
        time.sleep(3)
        elements = self.eosdo.find_elements(r'//table[@id="queues"]//tbody//tr', 20)
        rows = len(elements)
        for index in range(1, rows + 1):
            element = self.eosdo.find_element(fr'//table[@id="queues"]//tr[{index}]//td', 30)
            if element.get_attribute('colspan') == '9':
                queue = self.eosdo.find_element(
                    fr'//table[@id="queues"]//tr[{index}]//td//div[@class="form-control slct dropdown-toggle prevent-user-select disabled"][1]',
                    30).text
                sogl_list['лист_согласования'][queue] = []
            else:
                dict_queue = {
                    'фио': '',
                    'должность': '',
                    'подразделение': '',
                    'организация': '',
                    'решение': '',
                    'дата_решения': '',
                    'комментарии': '',
                    'вложения': []
                }
                fio = self.eosdo.find_element(fr'//table[@id="queues"]//tr[{index}]//td[3]').text
                position = self.eosdo.find_element(fr'//table[@id="queues"]//tr[{index}]//td[5]').text
                group = self.eosdo.find_element(fr'//table[@id="queues"]//tr[{index}]//td[6]').text
                organization = self.eosdo.find_element(fr'//table[@id="queues"]//tr[{index}]//td[7]').text
                solution = "Ожидается"
                date_solution = ""
                comments = ""
                dict_queue['фио'] = fio
                dict_queue['должность'] = position
                dict_queue['подразделение'] = group
                dict_queue['организация'] = organization
                dict_queue['решение'] = solution
                dict_queue['дата_решения'] = date_solution
                dict_queue['комментарии'] = comments
                sogl_list['лист_согласования'][queue].append(dict_queue)

        list_sogl = json.dumps(sogl_list, indent=4, ensure_ascii=False)
        logging.info('Лист согласования создан и записан в БД')
        return list_sogl

    @staticmethod
    def launcher_handler(timeout: int) -> None:
        """
        Закрытие окна Open EosdoJwsLauncher
        :param timeout: время ожидания появления окна
        :return:
        """
        try:
            logging.info('Ждем окно Open EosdoJwsLauncher')
            win = Desktop(backend="uia").window(title_re='^Open.*')
            win.wait('ready', timeout=timeout, retry_interval=1)
            win.set_focus()
            #
            #
            # win.wait("visible ready", timeout=timeout)
            logging.info('Окно Open EosdoJwsLauncher появилось, закрываем его')
            time.sleep(1)
            logging.info('Press Cancel')
            win['Open EosdoJwsLauncher.exe'].click_input(use_log=False)
        except Exception as err:
            logging.error(err)
            logging.info('Окно Open EosdoJwsLauncher не появилось! Продолжаем')

    @staticmethod
    def application_handler(timeout: int) -> None:
        """
        Закрытие окна Starting application
        :param timeout: время ожидания появления окна
        :return:
        """
        try:
            logging.info('Ждем окно Starting application')
            win = Desktop(backend="uia").window(title_re='^Starting.*')
            win.wait('ready', timeout=timeout, retry_interval=1)
            win.set_focus()
            logging.info('Окно Starting application появилось, закрываем его')
            logging.info('Press Cancel')
            win['CloseButton'].click_input(use_log=False)
        except Exception as err:
            logging.error(err)
            logging.info('Окно Starting application не появилось! Продолжаем')

    def exit_eosdo(self) -> None:
        """
        Функция выхода из ЕОСДО
        :return:
        """
        self.connection = False
        try:
            self.eosdo.find_element('//span[contains(text(),"Выйти")]', 20).click()
        except Exception as err:
            logging.error(f'Ошибка при выходе из ЕОСДО {err}')
        self.eosdo.close_site()

    @staticmethod
    def clean_fild(element):
        element.send_keys(Keys.CONTROL + 'a')
        element.send_keys(Keys.DELETE)
        time.sleep(1)

    def close_exporter(self):
        """
        Ожидание загрузки фалов
        :return:
        """
        try:
            if self.eosdo.exists_by_xpath(Selector.block, 1):
                logging.info('Ждем пока пропадет окно загрузки')
                WebDriverWait(self.eosdo.driver, 2).until(
                    EC.invisibility_of_element(
                        (By.XPATH, Selector.block)))  # ждем пока пропадет окно загрузки
                self.eosdo.find_element('//button[@id=".btnDialogClose"]', 2).click()  # закрываем вкладку
            else:
                self.eosdo.find_element('//button[@id=".btnDialogClose"]', 2).click()  # закрываем вкладку
        except TimeoutException:
            logging.info('Окно загрузки не пропадает. Нажимаю Esc')
            keyboard.send_keys("{ESC}")
