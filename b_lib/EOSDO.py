import time
from selenium import webdriver
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
import os
import logging as lg
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys


class Eosdo:
    """
    Класс для работы с селениумом
    """
    TIME_OUT = 15

    def __init__(self):
        self.options = webdriver.ChromeOptions()
        self.driver = None
        self.wt = None
        self.keys = Keys
        self.timeout = self.TIME_OUT

    def set_options(self, load_path, browser_path):
        self.options.add_experimental_option('excludeSwitches', ['enable-logging'])
        if browser_path:
            self.options.binary_location = browser_path
        if load_path:
            self.options.add_experimental_option('prefs', {'download.default_directory': load_path,
                                                           "safebrowsing.enabled": False,
                                                           "download.prompt_for_download": False,
                                                           "download.directory_upgrade": True,
                                                           })

    def set_driver(self, browser, driver_path):
        if browser == 'IE':
            self.driver = webdriver.Ie(executable_path=driver_path)
        elif browser == 'chrome':
            self.driver = webdriver.Chrome(options=self.options, executable_path=driver_path)
        self.wt = WebDriverWait(self.driver, timeout=self.timeout)

    def open_site(self, site_url, driver_path, browser='chrome', browser_path=None, load_path=None, max_tries=5):
        self.set_options(load_path, browser_path)
        self.set_driver(browser, driver_path)
        while max_tries > 0:
            try:
                lg.info(f'Open URL:{site_url}')
                self.driver.get(site_url)
                self.driver.maximize_window()
                return
            except Exception as err:
                max_tries -= 1
                lg.error(f'Сайт не открылся {err}. Пробую повторно открыть')
                self.close_site()
                time.sleep(60)
        lg.error(f'Попытки открыть сайт исчерпаны')
        raise

    def scroll_to_element(self, selector):
        element = self.find_element(selector, 10)
        self.driver.execute_script("arguments[0].scrollIntoView();", element)

    def wait_loading_window(self, selector, timeout):
        if self.exists_by_xpath(selector, 2):
            wt = WebDriverWait(self.driver, timeout)
            # Ожидание загрузки страницы
            wt.until(EC.invisibility_of_element((By.XPATH, selector)))

    def close_site(self):
        try:
            self.driver.implicitly_wait(2)
            lg.info("Идет завершение сессии...")
            self.driver.quit()
            lg.info("Драйвер успешно завершил работу.")
        except Exception as err:
            # возможно стоит выводить тип ошибки трассировку
            lg.info(f"Произошла ошибка при завершении работы с браузером: '{err}'")
            os.system("tskill chrome")
            # noinspection SpellCheckingInspection
            lg.info('Chrome браузер закрыт принудительно.')
            os.system("tskill chromedriver")
            lg.info('Chrome драйвер закрыт принудительно.')

    def find_element(self, selector, timeout=None, action='off'):
        if timeout:
            wt = WebDriverWait(self.driver, timeout=timeout)
            # Ожидание загрузки страницы
            wt.until(EC.element_to_be_clickable((By.XPATH, selector)))
        if action == 'on':
            element = self.driver.find_element(By.XPATH, selector)
            self.driver.execute_script("arguments[0].scrollIntoView();", element)
        return self.driver.find_element(By.XPATH, selector)

    def find_elements(self, selector, timeout=None):
        if timeout:
            wt = WebDriverWait(self.driver, timeout=timeout)
            # Ожидание загрузки страницы
            wt.until(EC.element_to_be_clickable((By.XPATH, selector)))
            return self.driver.find_elements(By.XPATH, selector)
        return self.driver.find_elements(By.XPATH, selector)

    def exists_by_xpath(self, xpath, timeout=None):
        try:
            if timeout:
                self.driver.implicitly_wait(timeout)
                self.find_element(xpath)
                return True
            else:
                self.find_element(xpath)
                return True
        except Exception:
            return False

    def double_click(self, selector, timeout=None):
        if timeout:
            wt = WebDriverWait(self.driver, timeout=timeout)
            # Ожидание загрузки страницы
            element = wt.until(EC.element_to_be_clickable((By.XPATH, selector)))
        else:
            wt = WebDriverWait(self.driver, timeout=0)
            # Ожидание загрузки страницы
            element = wt.until(EC.element_to_be_clickable((By.XPATH, selector)))
        actionChains = ActionChains(self.driver)
        actionChains.double_click(element).perform()

    def switch_to_active_tab(self):
        """
        переключиться на последнее открытое окно
        """
        self.driver.switch_to.window(self.driver.window_handles[-1])

    def switch_to_main(self):
        """
        переключиться на главное окно
        """
        self.driver.switch_to.window(self.driver.window_handles[0])

    def get_params_to_attach(self):
        """
        получить идентификаторы текущей сессии
        """
        if self.driver:
            return self.driver.command_executor._url, self.driver.session_id
        else:
            pass
            # raise ChromeDriverNotFoundException()

    def attach_to_session(self, executor_url, session_id):
        """
        подключиться к существующей сессии
        """
        original_execute = WebDriver.execute

        def new_command_execute(self, command, params=None):
            if command == "newSession":
                return {'success': 0, 'value': None, 'sessionId': session_id}
            else:
                return original_execute(self, command, params)

        WebDriver.execute = new_command_execute
        driver = webdriver.Remote(command_executor=executor_url, desired_capabilities={})
        driver.session_id = session_id
        WebDriver.execute = original_execute
        return driver