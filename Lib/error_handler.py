import os
import traceback
import pyautogui
import win32com
import win32com.client as win32
from datetime import datetime, timedelta
from threading import Thread
import logging
from Lib.b_outlook import BusinessOutlook


class ErrorHandler:
    """
        Класс для обработки ошибок в программных роботах.
        ver.3.4.3 (26.03.2021)
    """
    def __init__(self, name_def, config, tries_count=0, minutes_wait=None, attach_screen=False,
                 info=None, d_info_func=None, d_info_list_args=(), reraise=False):
        """
            Инициализация модуля происходит в начале оборачиваемого блока/функции.
            Запуск обработчика через контекстный менеджер:
                 - tries_count == 0 - при возникновении ошибки остановит робота и направит письмо;
                 - tries_count > 0 - при возникновении ошибки выполнит перезапуск блока {tries_count} раз.
            :name_def: название функции, которая добавляется в обработчик
            :config: конфигурация робота
            :tries_count: кол-во перезапусков блока. По умолчанию отключено.
            :minutes_wait: время при вызове таймера. По умолчанию 0 (вызов метода simple_error)
            :attach_screen: отправка скриншота при ошибках. По умолчанию отключено.
            :info: - строка, прописываемая в начале письма в техподдержку. По умолчанию отсутствует.
            :d_info_func: - функция, возвращающая string. Считывает динамическую информацию во время ошибки.
                Эта динамическая информация проставляется в письме.
            :reraise: варианты обработки ошибки.
                По умолчанию False - ошибка подавляется, роботу подается команда exit с выходным кодом.
                True - ошибка рейзится на уровень выше,
                None - ошибка подавляется, exit не вызывается, возвращается None.
        """
        self.try_num = 0
        self.config = config
        self.name_def = name_def
        self.robot_name = config.robot_name
        self.log_path = fr"{config.folder_logs}\{config.log_file}"
        # self.logger = logger                      # с logging это не нужно
        self.screen_shot_path = None
        self.tries_count = tries_count
        self.time_checker = None
        self.flag_to_stop_timer = False
        self.minutes_wait = minutes_wait
        self.attach_screen = attach_screen
        self.info = info
        self.reraise = reraise
        self.d_info_func = d_info_func
        self.d_info_list_args = d_info_list_args
        self.error = None

    def __enter__(self):
        """
            Является частью протокола контекстных менеджеров.
            Выполняется __init__, затем __enter__.
        """

        # Запуск таймера
        if self.minutes_wait:
            self.time_checker = Thread(name='time_checker', target=self.timer, args=(self.minutes_wait,))
            self.flag_to_stop_timer = False
            self.time_checker.start()
            return self.time_checker

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
            Действия при закрытии контекстного менеджера.
        """
        # Останавливаем таймер
        if self.time_checker:
            self.flag_to_stop_timer = True
            self.time_checker.join()
            del self.time_checker
        # Обрабатываем ошибки
        if exc_val:
            self.error = exc_val
            # При перезапусках - выполняется restart_block_on_error, иначе - simple_error
            if self.try_num > self.tries_count or not self.tries_count:
                self.simple_error()
            else:
                self.restart_block_on_error()
        return True    # При значении True, контекстный менеджер подавляет внутренний Exception

    def timer(self, minutes_wait):
        """
            Проверяет текущее время, если ожидаемое время истекло, направляет письмо в поддержку.
            После отправки сообщения робот продолжает работу.
            :minutes_wait: ожидаемое время выполнения выделенного блока(в минутах)
            Применение:
            eh = ErrorHandler(name_def, config, minutes_wait=5)
            while True:
                with eh:
                    your_function()
                    break
        """
        import pythoncom
        pythoncom.CoInitialize()
        start = datetime.now()
        while True:
            if not self.flag_to_stop_timer:
                # проверяем текущее время, если больше minutes_wait, направляем письмо в поддержку
                if datetime.now() - timedelta(minutes=minutes_wait) >= start:
                    outlook = None
                    try:
                        subject = f'TIME OUT in {self.robot_name}'
                        body = f'Ожидаемое время выполнения задачи: "{self.name_def}" '\
                                    f'превысило установленное значение: {str(minutes_wait)} минут!<br>'\
                                    f'Необходимо проверить работоспособность робота!'
                        if self.info:
                            body = f'Info: {self.info}<br>' + body
                        BusinessOutlook.send_mail(self.config.support_email, body, subject, recovery=True)
                        # Останавливаем таймер, чтобы исключить спам
                        self.flag_to_stop_timer = True
                    except Exception:
                        logging.error(f'Письмо не отправлено!\n'
                                          f'Ошибка при отправке письма:\n\n{traceback.format_exc()}')
                    finally:
                        del outlook
            else:
                # останавливаем таймер
                break

    def restart_block_on_error(self):
        """
            Выполняет перезапуск блока, создает скриншот на момент перезапуска, отправляет сообщение в поддержку.
            При успешном выполнении блока - выход из цикла(break). В случае ошибок - повтор(tries_count).
            :tries_count: количество попыток до остановки робота. Если tries_count=0 - вызов метода simple_error
            :attach_screen: направляет в письме скриншот при ошибке. По умолчанию отключено.
            Применение с контекстным менеджером:
            eh = ErrorHandler(name_def, config, tries_count=3)
            while True:
                with eh:
                    your_function()
                    break
            Применение с контекстным менеджером и таймером:
            eh = ErrorHandler(name_def, config, tries_count=3, minutes_wait=5)
            while True:
                with eh:
                    your_function()
                    break
        """
        trace = traceback.format_exc()
        logging.error(trace)
        logging.error(f'Ошибка в блоке: "{self.name_def}". Перезапуск блока.')
        self.try_num += 1
        if self.try_num > self.tries_count:
            logging.error('Кол-во попыток исчерпано, отправляем письмо в поддержку')
            self.simple_error()
        self.make_screen_time()
        logging.error(f'Попытка {str(self.try_num)} из {str(self.tries_count)}')
        # Уведомляю поддержку об ошибке и восстановлении
        subject = f'ERROR in "{self.robot_name}"'
        body = f'Ошибка в блоке: "{self.name_def}"<br>{"-"*50}<br>{trace}<br>{"-"*50}<br>' \
               f'Попытка восстановления № {str(self.try_num)} из {str(self.tries_count)}'
        BusinessOutlook.send_mail(self.config.support_email, body, subject, recovery=True)

    def simple_error(self):
        """
            При появлении ошибки отправляет письмо в поддержку, выполняет полную остановку робота.
            Применение с контекстным менеджером:
            with ErrorHandler(name_def, config):
                your_function()
            Применение с контекстным менеджером и таймером:
            with ErrorHandler(name_def, config, minutes_wait=5):
                your_function()
        """
        trace = traceback.format_exc()
        logging.error(trace)
        self.make_screen_time()
        try:
            subject = f'ERROR in "{self.robot_name}"'
            body = f'Ошибка в блоке: "{self.name_def}"<br>{"-"*50}<br>{trace}<br>{"-"*50}<br>' \
                   f'ПОПЫТОК ВОССТАНОВЛЕНИЯ ЭТОГО ШАГА НЕТ!'
            if self.info:
                body = f'Info: {self.info}<br>' + body
            if self.d_info_func:
                body = f'Dynamic_Info: {str(self.d_info_func(*self.d_info_list_args))}<br>' + body
            if self.reraise is False:
                body = body +'<br>ВНИМАНИЕ: ПРОЦЕСС ОСТАНОВЛЕН !!!'

            attach = [self.log_path, self.screen_shot_path] if self.attach_screen else [self.log_path]
            BusinessOutlook().send_mail(address=self.config.support_email,
                                        subject=subject,
                                        body=body,
                                        attachments=attach)
        except Exception:
            trace = traceback.format_exc()
            logging.error(f'Письмо не отправлено!\nОшибка при отправке письма:\n\n{trace}')

        # Выходим из робота, или возвращаем None, или ререйзим exception
        if self.reraise is None:
            pass
        elif not self.reraise:
            exit(1)                       # потоки могут зависнуть и не освобождаться
        else:
            raise self.error

    def make_screen_number(self, folder=None):
        """
            Выполняет скриншот и сохраняет в каталоге {folder}, подбирает имя по счетчику {counter}.
        """
        logging.info('make_screen_number')
        folder = self.get_folder(folder)
        counter = 1
        # перебирает {counter}, поиск свободного имени, шаблон: Screen_{counter}.jpg
        while os.path.exists(os.path.join(folder, f'Screen_{str(counter)}.jpg')):
            counter += 1
        self.screen_shot_path = os.path.join(folder, f'Screen_{str(counter)}.jpg')
        self.get_screen_shot()

    def make_screen_time(self, folder=None):
        """
            Выполняет скриншот и сохраняет в каталоге {folder}, указывает в имени текущее время {date} до милисекунд.
        """
        logging.info('make_screen_time')
        folder = self.get_folder(folder)
        date = datetime.now().strftime('%d%m%Y-%H_%M_%S_%f')
        self.screen_shot_path = os.path.join(folder, f'{date}.jpg')
        self.get_screen_shot()

    def get_screen_shot(self):
        logging.info('get_screen_shot')
        screen = pyautogui.screenshot()
        logging.info(f'Path to save: {self.screen_shot_path}')
        screen.save(self.screen_shot_path)

    def get_folder(self, folder):
        """ Если не указана директория для хранения скриншотов, создается папка {screen error} в корне проекта. """
        if folder is None:
            current_path = os.path.abspath(__file__)
            folder = current_path[:current_path.rfind("venv")] + 'screen error'
            root_dir = os.path.dirname(os.path.abspath(__file__))
            # folder = os.path.join(root_dir, 'screen error')
        if not os.path.exists(folder):
            logging.info('Создаю каталог: {}'.format(folder))
            os.mkdir(folder)
        logging.info(f'Dir to save: {folder}')
        return folder

    def mock_send_mail(self):
        logging.info('Mock-Mail send')
