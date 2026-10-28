"""Cross-version fixture from cryptography 46.0.3; synthetic key/data only."""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from .fields import EncryptedTextField


@override_settings(FIELD_ENCRYPTION_KEY='MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=')
class LegacyEncryptionCompatibilityTests(SimpleTestCase):
    # Produced by the previously deployed cryptography release, not this runtime.
    token = 'gAAAAABq4bFHAh5W5ywKxkqtD38Iq-QJh0xW_MY2jndAmxpLtf3zdmCdwR6_j0phNcBlFlc9hRRfwBkJsnTCfF7WCNfjoyuPUmU5MSuYFDazc9jJQCvOT5kmxC1NQfkCRPxmz51mMsRU'

    def test_pre_upgrade_ciphertext_remains_readable(self):
        self.assertEqual(EncryptedTextField().to_python('fernet:' + self.token),
                         'Fictional legacy integration value')

    def test_modified_legacy_ciphertext_is_still_rejected(self):
        altered = self.token[:50] + ('A' if self.token[50] != 'A' else 'B') + self.token[51:]
        with self.assertRaises(ImproperlyConfigured):
            EncryptedTextField().to_python('fernet:' + altered)
