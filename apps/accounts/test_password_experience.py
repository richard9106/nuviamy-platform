from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from .forms import PasswordSetupForm, PracticeSignupForm
from .password_validation import PasswordCharacterValidator


class PasswordFormatTests(SimpleTestCase):
    def test_each_requested_character_class_is_enforced_on_server(self):
        validator = PasswordCharacterValidator()
        for password in ('lowercase9!', 'UPPERCASE9!', 'MissingNumber!', 'MissingSpecial9', 'Spaces Alone 9', 'HiddenControl9\u200b', 'CombiningAccent9\u0301'):
            with self.subTest(password_kind=password), self.assertRaises(ValidationError):
                validator.validate(password)
        for password in ('DifferentUnique2026!', 'ÉlégantUnique9!'):
            validator.validate(password)
        with self.assertRaises(ValidationError):
            validate_password('Aa1!')

    def test_setup_form_uses_the_same_policy_and_retains_autocomplete(self):
        user = get_user_model()(username='fixture', email='fixture@example.invalid')
        form = PasswordSetupForm(user, data={'new_password1': 'lowercaseonly9!', 'new_password2': 'lowercaseonly9!'})
        self.assertFalse(form.is_valid())
        self.assertIn('new_password2', form.errors)
        self.assertEqual(form.fields['new_password1'].widget.attrs['autocomplete'], 'new-password')
        self.assertEqual(form.fields['new_password1'].widget.attrs['data-password-minimum'], 8)
        self.assertFalse(form.fields['new_password1'].widget.render_value)


@override_settings(MFA_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False)
class PasswordPageTests(TestCase):
    def test_signup_rejects_format_and_personal_information_without_creating_account(self):
        from .test_legal_acceptance import LegalAcceptanceTests
        data = LegalAcceptanceTests().payload()
        for password in ('missinguppercase9!', 'MissingNumber!', 'Fictional1!'):
            response = self.client.post(reverse('signup'), data | {'password1': password, 'password2': password})
            self.assertEqual(response.status_code, 200)
            self.assertIn('password1', response.context['form'].errors)
            self.assertFalse(get_user_model().objects.filter(email=data['email']).exists())

    def test_public_forms_provide_accessible_controls_without_password_echo(self):
        response = self.client.get(reverse('login'))
        self.assertContains(response, 'aria-label="Show password"')
        self.assertContains(response, 'data-password-toggle')
        from django.contrib.staticfiles.storage import staticfiles_storage
        self.assertContains(response, staticfiles_storage.url('password-tools.js'))
        response = self.client.get(reverse('signup'))
        self.assertContains(response, 'data-password-rule="lowercase"')
        self.assertContains(response, 'data-password-rule="uppercase"')
        self.assertContains(response, 'data-password-rule="special"')
        self.assertContains(response, 'data-password-rule="number"')
        self.assertContains(response, 'aria-live="polite"')
        self.assertEqual(PracticeSignupForm().password_minimum_length, 8)

    def test_existing_password_can_still_be_used_for_login(self):
        user = get_user_model().objects.create_user('legacy-password-fixture', 'legacy@example.invalid', 'existingpassword')
        response = self.client.post(reverse('login'), {'username': user.email, 'password': 'existingpassword'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)
