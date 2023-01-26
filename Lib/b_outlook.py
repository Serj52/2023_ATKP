import win32com, logging
import win32com.client as win32
import os
from datetime import datetime
import uuid
import time
import tkinter as tk
from tkinter import messagebox as mb
from CONFIG import Config as cfg
from pathlib import Path
from Lib.DATABASE import DateBase
from Lib.b_eosdo import BusinessEosdo
from Lib.b_eosdo import RABBIT
import json


HTML_STYLE = '<style>h5{font-style:italic;font-family:""Times New Roman""}</style>'


class BusinessOutlook:

    def connection(self, max_tries=3):
        while max_tries > 0:
            try:
                outlook = win32com.client.Dispatch('Outlook.Application')
                return outlook
            except Exception as err:
                logging.error(f'Пробую повторно подключиться к Outlook. Ошибка {err}')
                max_tries -= 1
                time.sleep(30)
        logging.error(f'Попытки подключиться к Outlook исчерпаны')
        raise

    def send_mail(self, address: str, subject, body=None, html_body=None, attachments=None, bcc=None):
        outlook = self.connection()
        logging.info('Run send_mail')
        mail = outlook.CreateItem(0)
        mail.To = address
        logging.info(f'Адрес получателя: {address}')
        mail.Subject = subject
        logging.info(f'Тема письма: {subject}')
        if bcc:
            logging.info(f'Скрытый email: {bcc}')
            mail.BCC = bcc
        if body:
            logging.info(f'Тело письма: {body}')
            mail.Body = body
        if html_body:
            logging.info(f'Тело письма: {html_body}')
            mail.HTMLBody = HTML_STYLE + html_body
        if attachments:
            for att in attachments:
                logging.info(f'Добавляю вложение: {att}')
                mail.Attachments.Add(Source=att)
        logging.info('Отправка письма...')
        mail.Send()
        logging.info(f'Письмо {address} отправлено успешно!')


    def start_end_process(self, what):
        logging.info('start_end_process')
        subject = str()
        if what == 'start':
            subject = 'Запущен основной процесс!'
        if what == 'end':
            subject = 'Оновной процесс завершен!'
        self.send_mail(cfg.support_email, subject)

    def get_inbox(self, max_tries=3):
        outlook = self.connection()
        while max_tries > 0:
            try:
                # Получаю пространство имен объекта
                namespace = outlook.GetNamespace("MAPI")
                # Получаю непрочитанные письма из папки "Входящие" (константа "6")
                inbox = namespace.GetDefaultFolder(6).Items.Restrict("[UnRead] = True")
                return inbox
            except Exception as err:
                logging.error(f'Пробую повторно получить непрочитанные письма из папки "Входящие". Ошибка {err}')
                max_tries -= 1
                time.sleep(30)
        logging.error(f'Попытки проверить письма в Outlook исчерпаны')
        raise

    def get_mail_data_by_subjects(self, themes, max_tries=3):
        """
        Получить данные письма по темам писем.\n
        Возвращает список, если запрашиваемые темы есть среди непрочитанных писем:\n
        0 - тема письма\n
        1 - тело письма\n
        2 - отправитель письма\n
        3 - ФИО отправителя письма\n
        4 - наименования вложений из письма с расширениями
        """
        # Преобразовываю список тем в строку для паттерна регулярных выражений
        # Получаю сом объект
        inbox = self.get_inbox()
        # Если есть непрочитанные письма ищу нужную тему и в случае успеха возвращаю это значение темы,
        # иначе - помечаю письмо прочитанным
        # Если нет новых писем прекращаю работу

        if inbox.COUNT:
            for item in inbox:
                # Извлекаю тему письма
                mail_theme = item.Subject.strip()
                # Перибираем название проектов
                for theme in themes:
                    if theme.lower() in mail_theme.lower():
                        logging.info(f"Получено письмо! Тема письма: [{mail_theme}]")
                        self.mail_process(item, theme)
                        break
                try:
                    item.UnRead = False
                # Иногда не удается пометить письмо как прочитанное (например уведомление об отзыве письма и др.)
                except Exception as ex:
                    message = f"Робот приостановлен. В outlook появился неопознанный элемент: {ex}"
                    logging.error(message, "error")
                    subject = "BusinessOutlook - ошибка!"
                    body = fr"{message}<br/>Пожалуйста проверьте и возобновите работу<br/>" \
                           r"<br/>--------------------------------------------------------" \
                           r"-------------------------------<br/>" \
                           "<i>Данное письмо сформировано автоматически программным роботом, " \
                           "отвечать на него не нужно.</i>"
                    self.send_mail(address=cfg.support_email, body=body, subject=subject)
                    # Стопаю робота, выбрасываю messagebox, жду саппорт...
                    root = tk.Tk()
                    root.withdraw()
                    mb.showwarning("Внимание!",
                                   "Робот приостановлен. В outlook появился неопознанный элемент, проверьте. "
                                   "После проверки, для возобновления работы робота нажмите 'ОК'")
                    root.destroy()
                    logging.error("Работа робота возобновлена.", "error")

    def generate_name_dirmail(self, dir_path):
        count = 1
        for dir in Path(dir_path).iterdir():
            if 'mail' in dir.name:
                count += 1
        return Path(dir_path, f'mail_{count}')

    def mail_process(self, item, theme, max_tries = 3):
        """

        :param item:
        :param theme:
        :return:
        """

        try:
            mail_body = item.Body
            logging.info(f"Тело письма: [\n{mail_body}].")
            logging.info("Извлекаю адрес отправителя письма...")
            if item.SenderEmailType == "EX":
                mail_from = item.Sender.GetExchangeUser().PrimarySmtpAddress
            else:
                mail_from = item.SenderEmailAddress
            logging.info(f"Адрес отправителя письма: [{mail_from}].")
            mail_from_name = item.SenderName
            logging.info(f"ФИО отправителя письма: [{mail_from_name}].")
            # Извлекаю и сохраняю вложения если есть
            attachments_path = []
            dir_mail = self.generate_name_dirmail(Path(cfg.folder_receiving, theme))
            for attachment in item.Attachments:
                path = Path(dir_mail, 'Attachments')
                os.makedirs(path, exist_ok=True)
                # Пропускаю не нужные файлы
                if str(attachment).endswith('.png'):
                    continue
                attachments_path.append(str(attachment))
                attachment.SaveAsFile(Path(path, str(attachment)))
                logging.info(f"Извлечено вложение письма: [{str(attachment)}].")

            if attachments_path:
                # Сохраняю тело письма
                # item.SaveAs(Path(dir_mail, f'{theme.lower()}.txt'), 0)
                reg_number = self.get_regnumber(theme)
                # получаем task_id
                task = DateBase().get_task('РЕГ_НОМЕР', reg_number)
                #Сверяем адрес на который отправлялась ТКП и адрес отправителя отета
                sender = self.get_sender(task, mail_from)
                date = DateBase().get_one(task, 'ДАТА_РЕГ', 'tuple')
                queue = DateBase().get_one(task, 'ЗАПРОС', 'dict')['header']['replayRoutingKey']
                # Мы предполагаем, что ответ будет от того же адреса куда мы отправили письмо
                DateBase().update_list_delivery(task, sender)

                with open(cfg.response_incoming_mail, 'r', encoding='utf-8') as file:
                    data = json.load(file)
                data['header']['id'] = id = str(uuid.uuid4())
                data['header']['sourceId'] = task
                data['header']['date'] = str(datetime.now())
                data['body']['поставщик'] = sender
                data['body']['номер'] = reg_number
                data['body']['mail'] = mail_from
                data['body']['дата'] = datetime.strptime(date, '%d.%m.%Y')
                data['body']['текст сообщения'] = mail_body
                data['body']['files'] = BusinessEosdo().encode_base64(os.path.join(dir_mail, 'Attachments'))
                data_json = json.dumps(data, indent=2, ensure_ascii=False)
                RABBIT.Rabbit().send_data_queue(queue, data_json)
                # записываю в БД отчет об отправке
                DateBase().response_db(id, data, 'ОТВЕТ_ПОСТАВЩИКА', task)
                item.UnRead = False
                return
            logging.info('В письме отсутствуют вложения. Направляю ответ')
            body = 'Добрый день.\n' \
                   'В письме отсутствует вложение с технико-коммерческим предложением.\n ' \
                   'Просьба приложить файл и прислать письмо повторно'
            self.send_mail(address=mail_from, subject=theme, body=body)
            item.UnRead = False
            return

        except Exception as ex:
            item.UnRead = True
            logging.error(f'Ошибка при мониторинге письма {ex}]')
            raise



    def get_regnumber(self, dir_name:str):
        """
        Заменяем '-' на '/' для поиска рег номера в БД
        Из формата '22-9.2-25' в формат '22-9.2/25'
        :param dir_name:
        :return:
        """
        index = dir_name.rfind('-')
        temp = list(dir_name)
        temp[index] = '/'
        reg_number = ''.join(temp)
        return reg_number

    def get_sender(self, task, from_mail):
        """
        Поиск организации 'reseivers_list.json' в папке проекта
        :param dir_name:
        :param from_mail:
        :return:
        """
        # with open(os.path.join(cfg.folder_receiving, dir_name, 'reseivers_list.json'), "r", encoding='utf-8') as file:
        #     reseivers_list = json.load(file)
        list_delivery = DateBase().get_one(task, 'СПИСОК_РАССЫЛКИ', 'dict')
        for organization, info in list_delivery.items():
            if from_mail == info['mail']:
                return organization
        logging.error(f'Ответ пришел с неизвестного адреса {from_mail}')
        raise
