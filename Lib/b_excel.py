
import openpyxl
import logging
import keyring



class Excel:
    @staticmethod
    def get_pwd(organization, file):
        workbook = openpyxl.load_workbook(file)
        worksheet = workbook.active
        max_row = worksheet.max_row
        pwd = ''
        for row in range(2, max_row + 1):
            value = worksheet.cell(row=row, column=1).value
            if value == organization:
                username = worksheet.cell(row=row, column=2).value
                pwd = keyring.get_password('eosdo', username)
                logging.info(f'Пароль для {organization} извлечен')
                workbook.close()
                return {'pwd': pwd, 'username': username}
        if pwd == '':
            logging.error(f'Проверьте наличие username для {organization} в {file}')
            workbook.close()
            raise

    def get_organization(self, file):
        workbook = openpyxl.load_workbook(file)
        worksheet = workbook.active
        max_row = worksheet.max_row
        organizations = []
        for row in range(2, max_row + 1):
            value = worksheet.cell(row=row, column=1).value
            if value is not None:
                organizations.append(value)
        return organizations
