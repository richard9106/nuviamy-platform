from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.practices.models import Practice
from .models import UserProfile


@override_settings(MFA_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False,
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'],
    STORAGES={'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
              'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class AppearanceTests(TestCase):
    def setUp(self):
        self.practice = Practice.objects.create(name='Appearance demo')
        self.user = get_user_model().objects.create_user('appearance-owner')
        self.profile = UserProfile.objects.create(user=self.user, practice=self.practice, role='owner')
        other = get_user_model().objects.create_user('another-owner')
        self.other_profile = UserProfile.objects.create(user=other, practice=self.practice, role='owner')
        self.client.force_login(self.user)
        self.url = reverse('appearance_preferences')

    def test_personal_preference_persists_after_new_login_and_renders(self):
        for theme in UserProfile.Theme.values:
            response = self.client.post(self.url, {'workspace_theme': theme, 'user_id': self.other_profile.user_id})
            self.assertRedirects(response, reverse('profile_settings') + '#appearance')
            self.profile.refresh_from_db()
            self.assertEqual(self.profile.workspace_theme, theme)
            self.other_profile.refresh_from_db()
            self.assertEqual(self.other_profile.workspace_theme, 'garden')
        fresh_client = Client()
        fresh_client.force_login(self.user)
        self.assertContains(fresh_client.get(reverse('profile_settings')), 'data-workspace-theme="coastal"')

    def test_unknown_value_and_get_cannot_change_preference(self):
        self.assertEqual(self.client.post(self.url, {'workspace_theme': 'bad-theme'}).status_code, 400)
        self.assertEqual(self.client.get(self.url).status_code, 405)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.workspace_theme, 'garden')

    def test_csrf_and_login_required(self):
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.user)
        self.assertEqual(protected.post(self.url, {'workspace_theme': 'rose'}).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.post(self.url, {'workspace_theme': 'rose'}).status_code, 302)

    def test_client_cannot_use_staff_preference_endpoint(self):
        self.profile.role = 'client'
        self.profile.save(update_fields=['role'])
        self.assertEqual(self.client.post(self.url, {'workspace_theme': 'rose'}).status_code, 403)

    def test_expired_trial_does_not_block_personal_appearance(self):
        self.practice.free_trial_ends_at = timezone.now() - timedelta(days=1)
        self.practice.save(update_fields=['free_trial_ends_at'])
        self.assertEqual(self.client.post(self.url, {'workspace_theme': 'rose'}).status_code, 302)
        self.profile.refresh_from_db()
        self.assertEqual(self.profile.workspace_theme, 'rose')
