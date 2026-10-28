"""Support content fails closed when its encryption key is unavailable."""
from django.core.exceptions import ImproperlyConfigured
from django.db import models
from cryptography.fernet import InvalidToken

from apps.practices.fields import get_fernet


class SupportEncryptedTextField(models.TextField):
    def get_prep_value(self, value):
        if value is None or value == '':
            return value
        # Always encrypt input, including strings that resemble a stored token.
        return 'fernet:' + get_fernet().encrypt(str(value).encode()).decode()

    def from_db_value(self, value, expression, connection):
        if value is None or value == '':
            return value
        try:
            if not value.startswith('fernet:'):
                raise InvalidToken
            return get_fernet().decrypt(value[7:].encode()).decode()
        except (InvalidToken, UnicodeDecodeError) as error:
            raise ImproperlyConfigured('Support content could not be decrypted.') from error
