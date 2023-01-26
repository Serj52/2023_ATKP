import random
import string



class Tools:

    def generator_id(self):
        letters_and_digits = string.ascii_letters + string.digits
        rand_string = ''.join(random.sample(letters_and_digits, 7))
        return rand_string