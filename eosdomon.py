from b_lib import log, EXCEPTION_HANDLER
import logging.config
import logging
import traceback
import time
from CONFIG import Config as cfg
from pywinauto import keyboard
from pywinauto import Desktop
from selenium.webdriver.common.keys import Keys
import json
import re
import os
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
import shutil
from b_lib.b_eosdo import BusinessEosdo
from b_lib.b_eosdo import Selector
from b_lib.b_post import BusinessPost
from eosdoreceive import EosdoReceive
from sender import Sender
from datetime import datetime
import uuid


class EosdoMon(BusinessEosdo):

    def __init__(self, eosdo_instance=None):
        self.files_added = False  # Статус добавления файлов
        self.task_dir = None
        self.project = None
        self.status = None
        self.data_for_send = ''
        self.list_sogl = None
        super().__init__()
        if eosdo_instance:
            self.__dict__['eosdo'] = eosdo_instance
            self.connection = True

    def exception_handler(self, task: str, organization: str) -> None:
        logging.error(f'Пробую повторно обработать запрос {task}.')
        self.reconect_eosdo(organization)
        try:
            self.eosdo.find_element(Selector.search_doc).click()
            self.search_document(task)
        except Exception as err:
            logging.error(f'Мониторинг документа по запросу {task} закончилось неудачно. {err}.')
            self.db.do_change_db(task, cfg.table_tasks, {'ОШИБКИ': 'Не предвиденная ошибка'})
            BusinessPost().send_mail(cfg.support_email, cfg.robot_name, f'Не предвиденная ошибка {err}')
            self.reconect_eosdo(organization)
            self.eosdo.find_element(Selector.search_doc).click()

    @EXCEPTION_HANDLER.exception_decorator
    def start_process(self, tasks: list, organization: str) -> None:
        """
        Мониторинг статусов документов в ЕОСДО
        :param tasks: список из номеров запросов из БД
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
            self.eosdo.find_element(Selector.search_doc).click()
        except Exception as err:
            logging.error(f'Ошибка {err}')
            # В случае ошибки повторно открываем ЕОСДО
            self.reconect_eosdo(organization)
            self.eosdo.find_element(Selector.search_doc).click()

        for task in tasks:
            logging.info(f'Начинаю мониторинг запроса: {task}')
            try:
                self.search_document(task)
            except Exception as err:
                trace = traceback.format_exc()
                logging.info(f'Мониторинг документа по запросу {task} закончилось неудачно. '
                             f'{err}.\n{trace}')
                # В случае ошибки повторно пытаемся обработать документ
                self.exception_handler(task, organization)
        try:
            self.eosdo.find_element(Selector.button_cansel).click()
        except Exception as err:
            logging.error(f'Ошибка {err}')
            # В случае ошибки повторно открываем ЕОСДО
            self.reconect_eosdo(organization)

        eosdo_incoming_tasks = self.db.get_sending_tasks(organization)
        if eosdo_incoming_tasks:
            logging.info(f'Начинаю мониторинг вх.документов в ЕОСДО для {organization}')
            EosdoReceive(self.eosdo).start_process(eosdo_incoming_tasks, organization)
            self.connection = False
        else:
            self.exit_eosdo()

    @EXCEPTION_HANDLER.exception_decorator
    def search_document(self, task: str) -> None:
        """
        Поиск документов в ЕОСДО
        :param task: номер запроса в ЕОСДО
        :return:
        """
        self.tools.clean_dir(cfg.saved_files)
        self.task = task
        self.queue = self.db.get_one(task, 'ЗАПРОС', cfg.table_tasks)['header']['replayRoutingKey']
        date = self.db.get_one(task, 'ДАТА_ПРОЕКТА', cfg.table_eosdo).strftime('%d.%m.%Y')
        self.project = self.db.get_one(task, 'НОМЕР_ПРОЕКТА', cfg.table_eosdo)
        # Очищаем дату регистрации
        element = self.eosdo.find_element(Selector.date_reg, 30)
        self.clean_fild(element)
        time.sleep(1)
        # Очищаем дату проекта
        element = self.eosdo.find_element(Selector.date_project, 10)
        self.clean_fild(element)
        # вбиваем дату
        self.eosdo.find_element(Selector.date_project, 20).send_keys(date)
        # Очищаем номер проекта
        element = self.eosdo.find_element(Selector.project_number, 10)
        self.clean_fild(element)
        # Вбиваем дату проекта
        self.eosdo.find_element(Selector.project_number).send_keys(self.project)
        # Нажимаем поиск
        self.eosdo.find_element(Selector.button_search_doc).click()
        logging.info(f'Проверяю статус проекта: {self.project}')
        # Заходим в карточку
        try:
            time.sleep(1)
            self.eosdo.double_click(fr'//span[text()="{self.project}"]', 10)
            time.sleep(1)
        except TimeoutException:
            logging.error(f'Не найден проект {self.project}')
            raise EXCEPTION_HANDLER.NotFoundDocument(f'Не найден проект {self.project}')
        # Проверяем статус
        self.status = self.eosdo.find_element(Selector.status_doc, 30).text.strip()
        logging.info(f'Статус документа: {self.status}')
        self.version = self.eosdo.find_element(Selector.version_doc, 30).text.strip()
        logging.info(f'Версия документа документа: {self.version}')
        if self.check_event(task):
            if self.status == 'Доработка':
                self.document_status_revision()
            elif self.status == 'Закрыт':
                self.document_status_closed(task)
            elif self.status == 'Подтверждение отправки на подписание в ЕОСДО':
                self.document_status_sending_confirmation(task)
            else:
                self.eosdo.find_element(Selector.button_cansel, 30).click()  # нажимаем отменить
                self.eosdo.find_element(Selector.button_clean, 30).click()
            # Записываем изменения в БД
            json_data = json.dumps(self.list_sogl, indent=4, ensure_ascii=False)
            self.db.do_change_db(task,
                                 cfg.table_eosdo,
                                 {'СТАТУС_ЕОСДО': self.status, 'ЛИСТ_СОГЛАСОВАНИЯ': json_data})
            # обновляю в БД дату проверки документа
            self.db.do_change_db(task, cfg.table_tasks)
            # Отправляем в шину лист согласования
            if self.status == 'Доработка':
                self.send_to_queue(task, code=1007)
            else:
                self.send_to_queue(task, code=1006)
        else:
            # обновляю в БД дату проверки документа
            self.db.do_change_db(task, cfg.table_tasks)
            # Выхожу из документа
            self.eosdo.find_element(Selector.button_cansel).click()
        logging.info(f'Мониторинг проекта: {self.project} завершен')

    def document_status_closed(self, task: str) -> None:
        """
        Обработка документов со статусом Закрыт
        :return:
        """
        self.eosdo.find_element(Selector.tab_main).click()
        # сохраняем номер и дату документа
        text = self.eosdo.find_element(Selector.reg_number).text
        reg_number = re.findall(r'\d{1,}-\d{1,}\S{0,}\d{1,}', text)[0]
        date = re.findall(r'\d{2}.\d{2}.\d{4}', text)[0]
        files = len(self.eosdo.find_elements(Selector.amount_added_files_close, 30))
        self.export_files(path=cfg.saved_files, amount_files=files)
        type_delivery = self.db.get_one(task, 'СПОСОБ_ОТПРАВКИ', cfg.table_tasks)
        logging.info(f'Способ доставки: {type_delivery}')
        if type_delivery == 'электронная почта' or type_delivery == 'смешанный':
            # list_sogl = json.dumps(self.list_sogl, indent=4, ensure_ascii=False)
            try:
                theme = f'{reg_number.replace("/", "-", 1)}_{date}'
                if Sender().sending(task, theme, self.project, self.queue):
                    self.db.do_change_db(
                        task,
                        cfg.table_eosdo,
                        {
                            'РЕГ_НОМЕР': reg_number,
                            'ДАТА_РЕГ': datetime.strptime(date, '%d.%m.%Y'),
                        }
                    )
                    self.db.do_change_db(
                        task,
                        cfg.table_tasks,
                        {
                            'СТАТУС': 'Отправлено',
                            'ТЕМА_ПИСЬМА': theme
                        }
                    )
                # если возникли ошибки при отправке
                else:
                    raise
            except Exception:
                self.db.do_change_db(
                    task,
                    cfg.table_eosdo,
                    {
                        'СТАТУС_ЕОСДО': self.status,
                        'РЕГ_НОМЕР': reg_number,
                        'ДАТА_РЕГ': datetime.strptime(date, '%d.%m.%Y')
                    }
                )
                self.eosdo.find_element(Selector.button_cansel, 30).click()  # нажимаем отменить
                self.eosdo.find_element(Selector.button_clean, 30).click()
                raise EXCEPTION_HANDLER.SendError('Ошибка отправки письма')
        self.eosdo.find_element(Selector.button_cansel, 30).click()  # нажимаем отменить
        self.eosdo.find_element(Selector.button_clean, 30).click()

    def document_status_revision(self) -> None:
        """
        Обработка документа со статусом Доработка
        :return:
        """
        self.eosdo.find_element(Selector.body).send_keys(Keys.PAGE_DOWN)  # спускаемся до Виз
        events = len(self.eosdo.find_elements(Selector.approve_rows))
        for row in range(1, events + 1):
            status = self.eosdo.find_element(f'{Selector.approve_rows}[{row}]//td[12]', 10).text.strip()
            if status == 'Отклонено' or status == 'Замечания нормоконтролера':
                # если есть вложения
                if self.eosdo.exists_by_xpath(f'{Selector.approve_rows}[{row}]//td[14]//button', 3):
                    fio_element = self.eosdo.find_element(f'{Selector.approve_rows}[{row}]//td[9]', 10).text
                    fio = fio_element.replace("(", "{(}").replace(")", "{)}")
                    approval_queue = self.eosdo.find_element(f'{Selector.approve_rows}[{row}]//td[6]', 10).text.strip(
                        ' ()')
                    # кликаем по скрепке
                    self.eosdo.find_element(f'{Selector.approve_rows}[{row}]//td[14]//button').click()
                    # сохраняем файлы
                    WebDriverWait(self.eosdo.driver, 30).until(
                        EC.visibility_of_element_located((By.XPATH, Selector.dialog_body)))
                    # выбираем все файлы в чекбоксе
                    self.eosdo.find_element(Selector.checkbox, 10).click()
                    element_text = self.eosdo.find_element(Selector.amount_files_checkbox).text
                    # число файлов для загрузки
                    amount_files = re.findall(r'\d{1,}[)]', element_text)[0].replace(')', '')
                    # сохраняем файлы в папку отклонившего
                    save_dir = os.path.join(cfg.saved_files, approval_queue, fio)
                    self.export_files(path=save_dir, amount_files=int(amount_files))
                    self.file_to_sogl(fio, approval_queue)  # Добавляем файлы в лист согласования
                    self.close_exporter()
        self.eosdo.find_element(Selector.button_cansel, 30).click()
        self.eosdo.find_element(Selector.button_clean, 30).click()
        # # отправляем файл в очередь ЕОСЗ
        # self.send_to_queue(task)
        # list_sogl = json.dumps(self.list_sogl, indent=4, ensure_ascii=False)
        # self.db.do_change_db(
        #     task,
        #     cfg.table_eosdo,
        #     {
        #         'СТАТУС_ЕОСДО': self.status,
        #         'ЛИСТ_СОГЛАСОВАНИЯ': list_sogl
        #     }
        # )
        # # обновляю в БД дату проверки документа
        # self.db.do_change_db(task, cfg.table_tasks)

    def send_to_queue(self, task: str, code=None) -> None:
        with open(cfg.response_sogl, 'r', encoding='utf-8') as out_file:
            logging.info(f'Записываю в json list_sogl')
            data = json.load(out_file)
        data["header"]["requestID"] = responseid = str(uuid.uuid4())
        data["header"]["sourceId"] = task
        data["header"]["date"] = str(datetime.now())
        data["code"] = code
        # добавляем в данные из шаблона лист согласования
        for key in self.list_sogl:
            data['body'][key] = self.list_sogl[key]
        data_json = json.dumps(data, indent=2, ensure_ascii=False)
        self.rabbit.send_data_queue(self.queue, data_json)
        self.db.response_db(responseid, data, 'Изменения в листе согласования', task)
        logging.info('В очередь отправлен лист согласования')

    def document_status_sending_confirmation(self, task: str) -> None:
        """
        Обработка документа со статусом Подтверждение отправки на согласование
        :return:
        """
        comment_normocontroler = False
        comment_otkloneno = False
        indices_comments = []  # для хранения индекса строк виз с Отклонениями и Замечаниями нормоконтролера
        indices_comments_normocontroler = []  # для хранения индекса строк виз с Замечаниями нормоконтролера
        rows = len(self.eosdo.find_elements(Selector.approve_rows))
        # перебираем Визы
        for row in range(1, rows + 1):
            status = self.eosdo.find_element(f'{Selector.approve_rows}[{row}]//td[12]', 10).text.strip()
            if status == 'Замечания нормоконтролера':
                # если есть вложения
                if self.eosdo.exists_by_xpath(f'{Selector.approve_rows}[{row}]//td[14]//button', 30):
                    indices_comments_normocontroler.append(row)
                    indices_comments.append(row)
                comment_normocontroler = True
            elif status == 'Отклонено':
                comment_otkloneno = True
                indices_comments.append(row)
        if comment_otkloneno:
            # Если есть замечания от других согласующих кроме Нормоконтролера
            self.events_handler(events=indices_comments, solution='otkloneno', task=task)
        elif comment_normocontroler and comment_otkloneno is False:
            self.events_handler(events=indices_comments, solution='normokontroler', task=task)

    def events_handler(self, events: list, solution: str, task: str) -> None:
        """
        Обработка Замечаний.
        :param task:
        :param events: список с индексами строк с Отклонениями или Замечаниями нормоконтролера.
        :param solution: 'normokontroler' or 'otkloneno'
        :return:
        """
        for index in events:
            # если есть вложения
            if self.eosdo.exists_by_xpath(f'{Selector.approve_rows}[{index}]//td[14]//button', 1):
                fio = self.eosdo.find_element(f'{Selector.approve_rows}[{index}]//td[9]', 10).text
                approval_queue = self.eosdo.find_element(fr'{Selector.approve_rows}[{index}]//td[6]',
                                                         10).text.strip(' ()')
                save_dir = os.path.join(cfg.saved_files, approval_queue, fio)
                # кликаем по скрепке сохранение файлов
                self.eosdo.find_element(f'{Selector.approve_rows}[{index}]//td[14]//button').click()
                WebDriverWait(self.eosdo.driver, 30).until(
                    EC.visibility_of_element_located((By.XPATH, Selector.dialog_body)))
                # ждем загрузку файлов в чекбоксе
                self.eosdo.find_element(fr'//div[@id="dialog_body"]//td//input', 30)
                element_text = self.eosdo.find_element(Selector.amount_files_checkbox).text
                # число файлов для загрузки
                amount_files = int(re.search(r'\d{1,}$', element_text)[0].strip())
                if solution == 'otkloneno':
                    # сохраняем все файлы т.к. будем отправлять на Доработку
                    self.select_all_checkbox(fio, approval_queue, amount_files)
                elif solution == 'normokontroler':
                    count_file = 0  # число файлов 'с принятыми правками НК'
                    # перебираем файлы в скрепке
                    for file in range(1, amount_files + 1):
                        name_file = self.eosdo.find_element(
                            fr'//table[@id="component15-files"]//tbody//tr[{file}]//td[4]',
                            10).text.lower().strip()
                        extensions_file = self.eosdo.find_element(f'{Selector.tbody}//tr[{file}]//td[7]').text.strip()
                        if 'с принятыми правками нк' in name_file and 'DOC' in extensions_file:
                            # кликаем по чекбоксу
                            self.eosdo.find_element(fr'{Selector.tbody}//tr[{file}]//td[2]//input').click()
                            count_file += 1
                    if count_file != 0:
                        # сохраняем файлы в папку отклонившего
                        self.export_files(path=save_dir, amount_files=count_file)
                        self.eosdo.find_element(Selector.body).send_keys(Keys.PAGE_UP)
                        self.eosdo.find_element(Selector.doc_page).click()
                        dir_path = fr'{cfg.saved_files}\{approval_queue}\{fio.replace("(", "{(}").replace(")", "{)}")}'
                        self.add_file(dir_path)
                        self.mark_as_main()
                        logging.info('Отправляем на подписание')
                        self.eosdo.find_element(Selector.senddraft).click()  # на подписание
                        self.eosdo.find_element(Selector.button_clean, 30).click()
                        # # Записываем всю информацию в БД
                        # list_sogl = json.dumps(self.list_sogl, indent=4, ensure_ascii=False)
                        # self.db.do_change_db(
                        #     task,
                        #     cfg.table_eosdo,
                        #     {
                        #         'СТАТУС_ЕОСДО': self.status,
                        #         'ЛИСТ_СОГЛАСОВАНИЯ': list_sogl
                        #     }
                        # )
                        # # обновляю в БД дату проверки документа
                        # self.db.do_change_db(task, cfg.table_tasks)
                        # Отправляем в ЕОСЗ sogl
                        # self.send_to_queue(task)
                        return
                    else:
                        # если файлов 'с принятыми правками НК' не найдено, то сохраняем все файлы Отклонившего
                        self.select_all_checkbox(fio, approval_queue, amount_files)
                else:
                    logging.error('Проверьте имя параметра flag для events_handler()')
                    raise

        logging.info('Нажимаем на Доработку')
        self.eosdo.find_element(Selector.senddraftsignin).click()  # на доработку
        self.eosdo.find_element(Selector.button_clean, 30).click()
        # если файлов 'с принятыми правками НК' не найдено меняем статус в sogl на Доработку
        self.list_sogl['статус'] = self.status = 'Доработка'
        # # Отправляем в ЕОСЗ sogl
        # self.send_to_queue(task)
        # list_sogl = json.dumps(self.list_sogl, indent=4, ensure_ascii=False)
        # self.db.do_change_db(
        #     task,
        #     cfg.table_eosdo,
        #     {
        #         'СТАТУС_ЕОСДО': 'Доработка',
        #         'ЛИСТ_СОГЛАСОВАНИЯ': list_sogl,
        #     }
        # )
        #
        # self.db.do_change_db(
        #     task,
        #     cfg.table_tasks,
        #     {
        #         'СТАТУС': 'Мониторинг'
        #     }
        # )

    def select_all_checkbox(self, fio: str, approval_queue: str, amount_files: int) -> None:
        """
        Выбираем все файлы в чекбоксе и экспортируем
        :param fio: - ФИО отклонившего
        :param approval_queue: очередь согласования
        :param amount_files: ФИО отклонившего
        """
        save_dir = os.path.join(cfg.saved_files, approval_queue, fio)
        self.eosdo.find_element(Selector.all_in_checkbox).click()  # выбираем все файлы в чекбоксе
        self.export_files(path=save_dir, amount_files=amount_files)  # сохраняем файлы в папку отклонившего
        self.file_to_sogl(fio, approval_queue)  # Добавляем файлы в лист согласования
        self.close_exporter()

    def mark_as_main(self, max_tries=3) -> None:
        """
        Омтетить файл, как основной
        :param max_tries: число попыток
        """
        count_file = 0
        while max_tries > 0:
            try:
                if self.files_added:
                    elements = self.eosdo.find_elements(Selector.amount_added_files_close, 30)
                    for i in range(1, len(elements) + 1):
                        element = self.eosdo.find_element(Selector.amount_added_files_close, 30)
                        if 'принятыми правками нк' in element.text.lower():
                            element.click()
                            logging.info(f'Устанавливаю флаг основной для {element.text.lower()}')
                            self.eosdo.find_element(Selector.button_main).click()
                            count_file += 1
                            time.sleep(2)
                            return
                        else:
                            element.click()
                            logging.info(f'Снимаю флаг основной с  {element.text.lower()}')
                            self.eosdo.find_element(Selector.button_main).click()
                            time.sleep(2)
                    if count_file == 0:
                        logging.error('Файлы "принятыми правками нк" не найдены')
                        raise EXCEPTION_HANDLER.NotFoundDocument('Файлы "принятыми правками нк" не найдены')
            except TimeoutException as err:
                max_tries -= 1
                logging.info('Окно загрузки не пропадает. Нажимаю Esc')
                keyboard.send_keys("{ESC}")
                print(f'Ошибка при установки флага "Основной" {err}')
        logging.error('Файлы не загрузились')
        raise

    def add_file(self, path: str, max_tries=120) -> None:
        """
        Загрузка файлов в карточку
        :param path: папка с файлами
        :param max_tries: число попыток открыть проводник
        """
        self.eosdo.find_element('//button[@id=".btnCheckout"]').click()
        logging.info(f'Выбран режим Редактирование')
        while max_tries > 0:
            files_before = len(self.eosdo.find_elements(Selector.amount_added_files_close, 30))
            logging.info(f'Число файлов до загрузки {files_before}')
            self.eosdo.find_element(Selector.button_add_file, 30).click()
            if self.eosdo.exists_by_xpath(Selector.button_close, 2):
                self.eosdo.find_element(Selector.button_close).click()
                max_tries -= 1
            else:
                logging.info('Проводник открылся')
                win = Desktop(backend="uia").window(title_re='Open')
                win['File Name:'].click_input()
                keyboard.send_keys(fr"{path}", with_spaces=True)
                for i in win.child_window(title="Items View", control_type="List").wrapper_object():
                    # if i.element_info.name.lower() == 'input':
                    i.click_input(button='left', pressed='control')
                    files_before += 1
                win.child_window(title="Open", auto_id="1", control_type="Button").click_input()
                try:
                    if self.eosdo.exists_by_xpath(Selector.block, 2):
                        logging.info('Ждем окно загрузки')
                        WebDriverWait(self.eosdo.driver, 10).until(EC.invisibility_of_element(
                            (By.XPATH, Selector.block)))
                        time.sleep(2)
                    files_after = len(self.eosdo.find_elements(Selector.amount_added_files_close, 10))
                    logging.info(f'Файлов должно быть {files_before}')
                    if files_after != files_before:
                        logging.info('Файлы не загрузились. Повторяю загрузку')
                        max_tries -= 1
                        continue
                    logging.info('Файлы загрузились')
                    self.files_added = True
                    return
                except TimeoutException:
                    logging.info('Окно загрузки не пропадает. Нажимаю Esc')
                    keyboard.send_keys("{ESC}")
                    files_after = len(self.eosdo.find_elements(Selector.amount_added_files_close, 30))
                    if files_after != files_before:
                        logging.info(f'Файлы не загрузились. Ожидалось {files_before}. Повторяю загрузку')
                        max_tries -= 1
                        continue
                    self.files_added = True
                    logging.info('Файлы загрузились. ')
                    return
        logging.error('Проводник не открылся')
        self.files_added = False
        raise

    def check_event(self, task: str) -> bool:
        """
        Есть ли изменения в документе
        :return: False or True
        """
        change = False
        logging.info('Открываю вкладку "Согласование и подписание"')
        self.eosdo.find_element(Selector.tab_approval).click()
        events = len(self.eosdo.find_elements(Selector.approve_rows, 30))
        sogl_list = self.db.get_one(task, 'ЛИСТ_СОГЛАСОВАНИЯ', cfg.table_eosdo)
        for event in range(1, events + 1):
            fio = self.eosdo.find_element(f'{Selector.approve_rows}[{event}]//td[9]', 10).text
            comment = self.eosdo.find_element(f'{Selector.approve_rows}[{event}]//td[13]', 10).text
            solution = self.eosdo.find_element(f'{Selector.approve_rows}[{event}]//td[12]', 10).text
            approval_queue = self.eosdo.find_element(fr'{Selector.approve_rows}[{event}]//td[6]',
                                                     10).text.strip(' ()')
            date_solution = self.eosdo.find_element(f'{Selector.approve_rows}[{event}]//td[7]', 10).text
            for queue in sogl_list["лист_согласования"][approval_queue]:
                if queue['фио'] == fio:
                    if queue['решение'] != solution:
                        logging.info(f"Есть изменения в решении {fio}. Было {queue['решение']} стало {solution}")
                        queue['решение'] = solution
                        queue['дата_решения'] = date_solution
                        queue['комментарии'] = comment
                        change = True
                        break
        # Сравниваем версию открытой карточки с версией из листа согласования
        version = self.eosdo.find_element(Selector.version_doc, 10).text
        if sogl_list["статус"] != self.status:
            sogl_list["статус"] = self.status
            change = True
        if version != sogl_list["версия"]:
            logging.info('Есть изменения в листе согласования')
            sogl_list["версия"] = version
            change = True
        if change:
            self.list_sogl = sogl_list
            logging.info('Изменения внесены в Лист согласования')
            return True
        else:
            return False

    def compare_columns(self):
        """
        Сравнение расположения колонок в документ
        :return: True or False
        """
        count_columns = len(
            self.eosdo.find_elements('//table[@class="table table-striped dataTable treetable"]/thead//th', 20))
        column_name = []
        for column in range(1, count_columns + 1):
            text_element = self.eosdo.find_element(
                f'//table[@class="table table-striped dataTable treetable"]/thead//th[{column}]').text
            column_name.append(text_element)
        templates = ''.join(column_name)
        if templates == cfg.column_order:
            return True
        else:
            return False

    def remove_dir(self, dir, max_tries=5):
        """
        Удаление директории
        :param dir: папка для удаления
        :param max_tries: число попыток
        """
        while True:
            if max_tries == 0:
                logging.error(f' Удалить папку {self.task_dir} не удалось')
                raise
            else:
                shutil.rmtree(self.task_dir)
                if dir in os.listdir(dir):
                    logging.info(f' Повторная попытка удалить папку {dir} ')
                    time.sleep(5)
                    max_tries -= 1
                    continue
                logging.info(f'Папка {self.task_dir} удалена')
                break

    def file_to_sogl(self, fio: str, approval_queue: str):
        """
        Записываю сохраненные файлы в лист согласования
        :param fio: ФИО согласующего
        :param approval_queue: очередь согласования
        """
        files_encoded = self.tools.encode_base64(fr"{cfg.saved_files}\{approval_queue}\{fio}")
        for queue in self.list_sogl["лист_согласования"][approval_queue]:
            if queue['фио'] == fio:
                queue['вложения'].append(files_encoded)
                logging.info(f'Вложения внесены в лист согласования для {fio} в очередь {approval_queue}')
                break


if __name__ == '__main__':
    log.set_2(cfg)
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
    })

    logging.info('\n\n=== Start ===\n\n')
    logging.info(f'Режим запуска: {cfg.mode}')
    eosdo = EosdoReceive()
    eosdo.start_process("АО \"Гринатом\"")
