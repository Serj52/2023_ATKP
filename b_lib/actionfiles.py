import random
import string
import os
import shutil
import base64
import logging
from pathlib import Path


class ActionFiles:

    def generator_id(self):
        letters_and_digits = string.ascii_letters + string.digits
        rand_string = ''.join(random.sample(letters_and_digits, 7))
        return rand_string

    @staticmethod
    def clean_dir(path: str) -> None:
        for file in os.listdir(path):
            if os.path.isdir(os.path.join(path, file)):
                shutil.rmtree(os.path.join(path, file), ignore_errors=False)
            else:
                os.remove(os.path.join(path, file))
        logging.info(f'Директория {path} очищена')

    @staticmethod
    def encode_base64(folder_path):
        """
        """
        result = []
        for file in Path(folder_path).iterdir():
            files_encoded = {}
            with open(file, 'rb') as f:
                doc64 = base64.b64encode(f.read())
                logging.info(f'Закодировал {file} в base64')
                doc_str = doc64.decode('utf-8')
                files_encoded['file_name'] = file.name
                files_encoded['file'] = doc_str
                result.append(files_encoded)

        if result:
            return result
        else:
            logging.error(f'Директория {folder_path} пустая')
            raise

    @staticmethod
    def move_to_reseiving(from_dir, to_dir):
        """
        Переместить файлы из папки Saved_files в папку проекта
        :param dir_name: Имя папки проекта
        :return:
        """
        for file in Path(from_dir).iterdir():
            shutil.move(str(file), to_dir)
            logging.info(f'Файл {file} перенесен в {to_dir}')