import json
import uuid
from datetime import datetime
from CONFIG import Config as cfg
import logging.config
import logging.handlers
import logging
import os
from b_lib.b_post import BusinessPost
from b_lib.other_tools import Tools
from b_lib.b_eosdo import RABBIT
from b_lib.DATABASE import DateBase
from b_lib.RABBIT import Rabbit
from b_lib import log
from pathlib import Path
import shutil
from b_lib import EXCEPTION_HANDLER


class Sender:

    def __init__(self):
        self.task = None

    @staticmethod
    def move_to_reseiving(from_dir, to_dir):
        """
        Переместить файлы из папки Saved_files в папку проекта
        :param dir_name: Имя папки проекта
        :return:
        """
        dir_path = os.path.join(cfg.folder_receiving, to_dir)
        for file in Path(from_dir).iterdir():
            shutil.move(str(file), dir_path)
            logging.info(f'Файл {file} перенесен в {dir_path}')

    def sending(self, task, theme, project, queue):
        errors = False
        reseiver_list = DateBase().get_one(task, 'СПИСОК_РАССЫЛКИ', cfg.table_tasks)
        dir_path = os.path.join(cfg.folder_receiving, theme)
        os.makedirs(dir_path)
        self.move_to_reseiving(from_dir=cfg.saved_files, to_dir=theme)
        #####################
        files_list = []
        # т.к. может быть несколько сохраненных документов из карточки документа:
        # сам запрос и его копия подписанная ЭП, проверям есть ли файл с ЭП
        elsign_file = None
        file_zapros = None
        for file in Path(cfg.folder_receiving, theme).iterdir():
            if 'запрос' in file.name.lower():
                file_zapros = str(file)
            elif 'электронный_документ' in file.name.lower():
                elsign_file = str(file)
        if elsign_file:
            files_list.append(str(elsign_file))
        else:
            files_list.append(str(file_zapros))

        for organization in reseiver_list:
            if reseiver_list[organization]['type'] == 'отрослевая':
                reseiver_list[organization]['статус'] = 'отправлено'
            else:
                address = reseiver_list[organization]['mail']
                try:
                    BusinessPost().send_mail(address=address,
                                             subject=theme,
                                             body=cfg.body_mail,
                                             attachments=files_list)
                    reseiver_list[organization]['статус'] = 'отправлено'
                except Exception as err:
                    errors = True
                    logging.error(f'Ошибка отправки письма для {address}: {err}.')
                    reseiver_list[organization]['статус'] = 'ошибка'

        DateBase().add_delivery_list(task, reseiver_list)
        logging.info(f'Отправка писем окончена')
        #Направляем отчет в шину о рассылке ТКП
        with open(cfg.response_send, 'r', encoding='utf-8') as out_file:
            logging.info(f'Записываю в json отчет о рассылке')
            data = json.load(out_file)
        data["header"]["id"] = id = str(uuid.uuid4())
        data["header"]["sourceId"] = task
        data["header"]["date"] = str(datetime.now())
        data["body"]["проект"] = project
        data["body"]["reseivers_list"] = reseiver_list
        data_json = json.dumps(data, indent=2, ensure_ascii=False)
        Rabbit().send_data_queue(queue, data_json)
        #Делаем запись в журнал об отправке сообщения
        DateBase().response_db(id, data, 'Отчет о рассылке ТКП', task)
        if errors:
            return False
        return True


    def generate_name_dirmail(self, dir_path):
        count = 1
        for dir in Path(dir_path).iterdir():
            if 'mail' in dir.name:
                count += 1
        return Path(dir_path, f'mail_{count}')

    def check_mail(self, task, from_mail):
        """
        Сверка электоронных адресов
        :param task:
        :param from_mail:
        :return:
        """
        address_found = False
        list_delivery = DateBase().get_one(task, 'СПИСОК_РАССЫЛКИ', cfg.table_tasks)
        supplier = ''
        for organization, info in list_delivery.items():
            if from_mail == info['mail']:
                list_delivery[organization]['статус'] = 'получен'
                address_found = True
                data_json = json.dumps(list_delivery, indent=2, ensure_ascii=False)
                DateBase().do_change_db(task, cfg.table_tasks, {'СПИСОК_РАССЫЛКИ': data_json})
                supplier = organization
                break
        if address_found:
            #статус ответов
            no_answer = False
            #проверяем СПИСОК РАССЫЛКИ повторно на предмет полученных сообщений
            for organization in list_delivery:
                if list_delivery[organization]['статус'] == 'отправлено':
                    no_answer = True
            if no_answer == False:
                logging.info(f'По запросу {task} получены ответы от всех предприятий. Записываю в БД статус Закрыт')
                DateBase().do_change_db(task, cfg.table_tasks, {'СТАТУС': 'Закрыт'})
            return supplier
        else:
            logging.error(f'Ответ пришел с неизвестного адреса {from_mail}')
            raise

    @EXCEPTION_HANDLER.exception_decorator
    def receiving(self):
        try:
            themes = [dir.name for dir in Path(cfg.folder_receiving).iterdir()]
            messages = BusinessPost().get_mail_data_by_subjects(themes)
            for message in messages:
                # Извлекаю и сохраняю вложения если есть
                attachments_path = []
                dir_mail = self.generate_name_dirmail(Path(cfg.folder_receiving, message["theme"]))
                for attachment in message["attachments"]:
                    path = Path(dir_mail, 'Attachments')
                    os.makedirs(path, exist_ok=True)
                    # Пропускаю не нужные файлы
                    if str(attachment).endswith('.png'):
                        continue
                    attachments_path.append(str(attachment))
                    attachment.SaveAsFile(Path(path, str(attachment)))
                    logging.info(f"Извлечено вложение письма: [{str(attachment)}].")
                    # Сохраняю тело письма
                    message["item"].SaveAs(Path(dir_mail, f'{message["theme"]}.txt'), 0)
                    # получаем task_id
                    self.task = DateBase().get_task('ТЕМА_ПИСЬМА', message["theme"])
                    supplier = self.check_mail(self.task, message["mail_from"])
                    reg_number = DateBase().get_one(self.task, 'РЕГ_НОМЕР', cfg.table_eosdo)
                    #Сверяем адрес на который отправлялась ТКП и адрес отправителя ответа
                    date = DateBase().get_one(self.task, 'ДАТА_РЕГ', cfg.table_eosdo)
                    queue = DateBase().get_one(self.task, 'ЗАПРОС', cfg.table_tasks)['header']['replayRoutingKey']
                    # Мы предполагаем, что ответ будет от того же адреса куда мы отправили письмо
                    # DateBase().update_list_delivery(task, message["mail_from"])
                    with open(cfg.response_incoming_mail, 'r', encoding='utf-8') as file:
                        data = json.load(file)
                    data['header']['id'] = id = str(uuid.uuid4())
                    data['header']['sourceId'] = self.task
                    data['header']['date'] = str(datetime.now())
                    data['body']['поставщик'] = supplier
                    data['body']['номер'] = reg_number
                    data['body']['электронный адрес ответа'] = message["mail_from"]
                    data['body']['дата'] = datetime.strftime(date, '%d.%m.%Y')
                    data['body']['текст сообщения'] = message['mail_body']
                    data['body']['files'] = Tools().encode_base64(os.path.join(dir_mail, 'Attachments'))
                    data_json = json.dumps(data, indent=2, ensure_ascii=False)
                    RABBIT.Rabbit().send_data_queue(queue, data_json)
                    # записываю в БД отчет об отправке
                    DateBase().response_db(id, data, 'ОТВЕТ_ПОСТАВЩИКА', self.task)
            for theme in themes:
                try:
                    task = DateBase().get_task('ТЕМА_ПИСЬМА', theme)
                    task_status = DateBase().get_one(task, 'СТАТУС', cfg.table_tasks)
                    if task_status == 'Закрыт':
                        shutil.move(os.path.join(cfg.folder_receiving, theme), cfg.folder_processed)
                except TypeError as err:
                    logging.error(f'Ошибка {err} при мониторинге папки {theme}')
                    raise
        except Exception as err:
            raise EXCEPTION_HANDLER.ReceivingError(f'Ошибка мониторинга писем {err}')



if __name__ == '__main__':
    log.set_2(cfg)
    logging.config.dictConfig({
        'version': 1,
        'disable_existing_loggers': True,
    })

    logging.info('\n\n=== Start ===\n\n')
    # Sender().sending('13', '22-9.2/25')
    Sender().receiving()

