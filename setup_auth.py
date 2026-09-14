"""Collect a fresh installation's password from its SSH terminal."""
import getpass
import hashlib
import json
import os
from pathlib import Path
import secrets
import sys
import warnings


def initialize(root):
    if (root / 'auth.json').exists():
        print('Существующий пароль сохранён.')
        return
    try:
        with open('/dev/tty', 'w') as terminal:
            with warnings.catch_warnings():
                warnings.simplefilter('error', getpass.GetPassWarning)
                while True:
                    password = getpass.getpass('Задайте пароль менеджера (от 12 символов): ', stream=terminal)
                    if len(password) < 12:
                        print('Введите не менее 12 символов.', file=terminal)
                        continue
                    confirmation = getpass.getpass('Повторите пароль: ', stream=terminal)
                    if password == confirmation:
                        break
                    print('Пароли не совпали. Попробуйте ещё раз.', file=terminal)
    except (OSError, EOFError, getpass.GetPassWarning):
        sys.exit('An interactive SSH terminal is required to set the manager password.')
    salt = secrets.token_bytes(16)
    data = {'salt': salt.hex(), 'hash': hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 200000).hex()}
    with os.fdopen(os.open(root / 'auth.json', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'w') as out:
        json.dump(data, out)
    print('Пароль задан. Сохранён только его хеш.')

if __name__ == '__main__':
    initialize(Path('/data/awg-manager'))
