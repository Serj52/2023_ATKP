import random
import string
import base64
import logging
from pathlib import Path


class Tools:

    def generator_id(self):
        letters_and_digits = string.ascii_letters + string.digits
        rand_string = ''.join(random.sample(letters_and_digits, 7))
        return rand_string

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