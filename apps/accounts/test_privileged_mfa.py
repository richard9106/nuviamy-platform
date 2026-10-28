from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from cryptography.fernet import Fernet

from .security import requires_mfa


@override_settings(MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=True, EMAIL_TWO_STEP_REQUIRED=False,
                   FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode())
class PrivilegedMFATests(TestCase):
    def test_operator_must_enroll_before_dashboard_even_when_global_mfa_is_off(self):
        user = get_user_model().objects.create_user(username='operator', password='test-only-password', is_staff=True)
        self.assertTrue(requires_mfa(user))
        self.client.login(username='operator', password='test-only-password')
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('mfa_setup'), fetch_redirect_response=False)

    def test_operator_setup_is_available_and_regular_user_is_unaffected(self):
        user = get_user_model().objects.create_user(username='operator', password='test-only-password', is_superuser=True)
        self.client.login(username='operator', password='test-only-password')
        self.assertEqual(self.client.get(reverse('mfa_setup')).status_code, 200)
        user.is_superuser = False
        self.assertFalse(requires_mfa(user))

    @override_settings(MFA_PRIVILEGED_REQUIRED=False)
    def test_explicit_development_override_preserves_existing_policy(self):
        user = get_user_model()(is_staff=True)
        self.assertFalse(requires_mfa(user))
