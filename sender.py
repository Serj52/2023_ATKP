import json
import uuid
from datetime import datetime
from CONFIG import Config as cfg
import logging.config
import logging.handlers
import logging
import os
from Lib.b_outlook import BusinessOutlook
from Lib.DATABASE import DateBase
from Lib.RABBIT import Rabbit
from Lib import log
from pathlib import Path
import shutil
from Lib import EXCEPTION_HANDLER


class Sender:

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

    def sending(self, task, reg_number, project, queue):
        errors = False
        result = reg_number.find('/')
        if result != -1:
            dir_name = reg_number.replace('/', '-', 1)
            reseiver_list = DateBase().get_one(task, 'СПИСОК_РАССЫЛКИ', 'dict')
            # addresses = self.address_list(reseiver_list, dir_name)
            ###########################
            dir_path = os.path.join(cfg.folder_receiving, dir_name)
            os.makedirs(dir_path)
            self.move_to_reseiving(from_dir=cfg.saved_files, to_dir=dir_name)
            #####################
            files_list = []
            # т.к. может быть несколько сохраненных документов из карточки документа:
            # сам запрос и его копия подписанная ЭП, проверям есть ли файл с ЭП
            elsign_file = None
            file_zapros = None
            for file in Path(cfg.folder_receiving, dir_name).iterdir():
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
                        BusinessOutlook().send_mail(address=address,
                                                    subject=dir_name,
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
            #Делаем запись в журнал сообщений
            DateBase().response_db(id, data, 'Отчет о рассылке ТКП', task)
            if errors:
                return False
            return True
        else:
            logging.error('Проверьте формат регистрационного номера документа.'
                          'В номере должен быть символ "/"')
            raise

    @EXCEPTION_HANDLER.exception_decorator
    def receiving(self):
        try:
            themes = [dir.name for dir in Path(cfg.folder_receiving).iterdir()]
            BusinessOutlook().get_mail_data_by_subjects(themes)
            for theme in themes:
                try:
                    reg_number = BusinessOutlook().get_regnumber(theme)
                    task = DateBase().get_task('РЕГ_НОМЕР', reg_number)
                    task_status = DateBase().get_one(task, 'СТАТУС', 'tuple')[0]
                    if task_status == 'Закрыт':
                        shutil.move(os.path.join(cfg.folder_receiving, theme), cfg.folder_processed)
                except TypeError as err:
                    logging.error(f'Ошибка {err} при мониторинге папки {theme}')
                    raise
        except Exception as err:
            raise EXCEPTION_HANDLER.ReceivingError(f'Ошибка мониторинга писем {err}')
