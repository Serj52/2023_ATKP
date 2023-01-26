import keyring
import os



MODE = 'test'

class Config:
    mode = MODE
    robot_name = 'Отправка на регистрацию запроса/дозапроса АТКП в ЕОСДО'
    folder_root = os.path.dirname(os.path.abspath(__file__))
    response = os.path.join(folder_root, 'Templates', 'response.json')
    response_tkp_done = os.path.join(folder_root, 'Templates', 'response_tkp_done.json')
    response_sogl = os.path.join(folder_root, 'Templates', 'response_sogl.json')
    response_error = os.path.join(folder_root, 'Templates', 'response_error.json')
    response_send = os.path.join(folder_root, 'Templates', 'response_send.json')
    response_incoming_mail = os.path.join(folder_root, 'Templates', 'response_incoming_mail.json')
    send_data = os.path.join(folder_root, 'Send_data')
    send_error_dir = os.path.join(send_data, 'Send_error')
    folder_logs = os.path.join(folder_root, 'Logs')
    folder_receiving = os.path.join(folder_root, 'Receiving')
    folder_processed = os.path.join(folder_root, 'Processed')

    log_file = "robot.log"
    credentials_file = os.path.join(folder_root, 'Credentials', 'credentials.xlsx')
    #Настройки базы данных
    db_login = ''
    db_password = keyring.get_password('db', db_login)
    db_server = ''
    db_port = '5433'
    db_name = 'eosdo'
    #Настройки RabbitMQ
    rabbit_host = ''
    rabbit_login = ''  # Логин для подключения к серверу с rabbit
    rabbit_pwd = keyring.get_password('rabbit', '')  # Пароль для подключения к серверу с rabbit
    queue_request = 'atkp'
    queue_EOSZ = 'eosz'
    queue_error = ''
    rabbit_port = 5672  # Порт для подключения к серверу с rabbit
    path = '/'
    #Настройка почты
    support_email = ''
    robot_mail = ''
    server_mail = ""
    body_mail = '«Добрый день.\n' \
                'Вам был направлен запрос АТКП. Прошу рассмотреть и направить ответное ТКП.\n' \
                'Прошу воспользоваться функцией «Ответить» и не редактировать тему письма».'
    #Настройки ЕОСДО
    url = r''
    chrome_path = fr'{folder_root}\Chrome\Application\Chrome.exe'
    chrome_driver = fr'{folder_root}\Сhromedriver\chromedriver.exe'
    file_credentials = os.path.join(folder_root, 'Credentials', 'credentials.json')
    saved_files = os.path.join(folder_root, 'Saved_files')
    #настройка временных периодовD
    check_min = 30 #минуты между мониторингом документов
    last_day = 90 #дни по истечению которых записи из БД удаляются



