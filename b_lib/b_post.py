import win32com, logging
import win32com.client as win32
import os
from datetime import datetime
import uuid
import smtplib
import time
import tkinter as tk
from tkinter import messagebox as mb
from CONFIG import Config as cfg
from pathlib import Path
import traceback


class BusinessPost:

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
            HTML_STYLE = '<style>h5{font-style:italic;font-family:""Times New Roman""}</style>'
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

    def get_mail_data_by_subjects(self, themes):
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
        messages = []
        for item in inbox:
            # Извлекаю тему письма
            mail_theme = item.Subject.strip()
            # Перибираем название проектов
            for theme in themes:
                if theme.lower() in mail_theme.lower():
                    logging.info(f"Получено письмо! Тема письма: [{mail_theme}]")
                    message = self.mail_process(item, theme)
                    if message:
                        messages.append(message)
                    break
            try:
                item.UnRead = False
            # Иногда не удается пометить письмо как прочитанное (например уведомление об отзыве письма и др.)
            except Exception as ex:
                message = f"Робот приостановлен. В outlook появился неопознанный элемент: {ex}"
                logging.error(message, "error")
                subject = "BusinessPost - ошибка!"
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
        return messages

    def mail_process(self, item, theme):
        """
        :param item:
        :param theme:
        :return:
        """
        try:
            message = {}
            logging.info("Извлекаю информацию из письма")
            if item.SenderEmailType == "EX":
                mail_from = item.Sender.GetExchangeUser().PrimarySmtpAddress
            else:
                mail_from = item.SenderEmailAddress
            if item.Attachments.count:
                message['attachments'] = item.Attachments
                message['mail_from'] = mail_from
                message['mail_body'] = item.Body
                message['item'] = item
                message['theme'] = theme
                logging.info(message)
                item.UnRead = False
                return message
            logging.info('В письме отсутствуют вложения. Направляю ответ')
            body = 'Добрый день.\n' \
                   'В письме отсутствует вложение с технико-коммерческим предложением.\n ' \
                   'Просьба приложить файл и прислать письмо повторно'
            self.send_mail(address=mail_from, subject=theme, body=body)
            item.UnRead = False
            return message

        except Exception as ex:
            item.UnRead = True
            logging.error(f'Ошибка при мониторинге письма {ex}]')
            raise

    @staticmethod
    def send_smtp(from_mail, to, subject, text):
        logging.info('Отправляю письмо')
        try:
            conn = smtplib.SMTP(cfg.server_mail, 25)
            text = "From:{0}\nTo:{1}\nSubject:{2}\n\n{3}".format(from_mail, to, subject, text).encode("utf-8")
            conn.sendmail(from_mail, to, text)
        except Exception as err:
            logging.error(f'Письмо не отправлено:\n{err}\n'
                          f'Ошибка при отправке письма через SMTP:\n\n{traceback.format_exc()}')
            raise


if __name__ == '__main__':
    outlook = BusinessPost()
    outlook.get_mail_data_by_subjects(['22-9.2-30'])




