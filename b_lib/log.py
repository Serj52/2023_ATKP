"""Настройки logging."""

import os
import sys
import logging
import logging.handlers


# Подготовка логов
def __init_logs(config):
    """Подготовка логов под настройки. Шаблонный код."""

    # Вычисляю путь к последнему лог файлу (временный)
    last_log_path = fr"{config.folder_logs}\last_{config.log_file}"

    # Если нет директории для логов - создаю
    if not os.path.isdir(config.folder_logs):
        os.makedirs(config.folder_logs)

    # Если есть последний временный лог - удаляю его
    if os.path.exists(last_log_path):
        os.remove(last_log_path)

def set_1(config):
    """Настройка для logging №1.\n
    С ротацией логов по суткам.\n
    @by Kuznetsov"""

    # Подготовка логов
    __init_logs(config)

    # Конфигурация логов
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s %(lineno)4s %(funcName)-20s %(levelname)-7s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.handlers.TimedRotatingFileHandler(fr"{config.folder_logs}\{config.log_file}", when='midnight'),
            logging.StreamHandler(stream=sys.stdout)]
    )

    logging.info("*" * 100)
    logging.info("Для logging установлена конфигурация set_1.")

def set_2(config):
    """Настройка для logging №2.\n
    1-н общий лог и 1-н последний (самый свежий) лог.\n
    @by Vikharev"""

    # Подготовка логов
    __init_logs(config)

    # Инициализирую конфигурацию логов
    logging.basicConfig(
        level=logging.INFO,
        format=f"%(asctime)s *** %(funcName)30s *** %(lineno)4s *** %(levelname)8s *** %(message)8s",
        datefmt="%d.%m.%Y %H:%M:%S",
        handlers=[
            logging.handlers.RotatingFileHandler(fr"{config.folder_logs}\{config.log_file}",
                                                 maxBytes=int(1e+7), backupCount=1),
            logging.handlers.RotatingFileHandler(fr"{config.folder_logs}\last_{config.log_file}"),
            logging.StreamHandler(stream=sys.stdout)]
    )

    logging.info("*" * 50)
    logging.info("Для logging установлена конфигурация set_2.")


# Раскрасить логи в консоли
class Color:
    """Раскрасить логи в консоли"""

    # Это на случай, если в cmd отключены цветные символы (ANSI).
    os.system('')

    GREEN = '\033[38;2;0;150;50m'
    GREEN_BACK = '\033[48;2;0;150;50m'
    YELLOW = '\033[33m'
    YELLOW_BACK = '\033[48;2;255;150;50m'
    RED = '\033[38;2;255;0;0m'
    RED_BACK = '\033[48;2;255;0;0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    END = '\033[0m'

    # Красит логи библиотеки logging в консоли
    @staticmethod
    def logging_color(message, level="info", background=False):
        """Красит логи библиотеки logging в консоли\n
        * message - Текст лога\n
        * level - Уровень лога ('info'/'warn'/'error')\n
        * background - Красить фон лога, а не текст\n
        ПРИМЕР ИСПОЛЬЗОВАНИЯ: Color.logging_color('Мой текст лога', 'warn')"""
        if level == 'info':
            print(Color.GREEN if not background else Color.GREEN_BACK, Color.BOLD, sep='', end='')
            logging.info(message)
            print(Color.END, end='')
        elif level == 'warn':
            print(Color.YELLOW if not background else Color.YELLOW_BACK, Color.BOLD, sep='', end='')
            logging.warning(message)
            print(Color.END, end='')
        elif level == 'error':
            print(Color.RED if not background else Color.RED_BACK, Color.BOLD, sep='', end='')
            logging.error(message)
            print(Color.END, end='')
        else:
            raise Exception("Не удалось раскрасить текст лога!"
                            "Первым аргументом укажите string, "
                            "вторым (необязательный) 'info'/'warn'/'error', "
                            "третьим (необязательный) True/False")
