"""Password format requirements for newly chosen passwords; never recheck login secrets."""
import unicodedata

from django.core.exceptions import ValidationError


class PasswordCharacterValidator:
    def validate(self, password, user=None):
        categories = {unicodedata.category(char) for char in password}
        missing = []
        if 'Ll' not in categories:
            missing.append('a lowercase letter')
        if 'Lu' not in categories:
            missing.append('an uppercase letter')
        if 'Nd' not in categories:
            missing.append('a number')
        if not any(unicodedata.category(char)[0] in {'P', 'S'} for char in password):
            missing.append('a special character (not a space)')
        if missing:
            raise ValidationError('Include %(requirements)s.', code='password_missing_characters',
                                  params={'requirements': ', '.join(missing)})

    def get_help_text(self):
        return 'Include a lowercase letter, an uppercase letter, a number and a special character (not a space).'
