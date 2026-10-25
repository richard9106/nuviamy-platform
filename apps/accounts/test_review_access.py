from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.practices.models import Practice, TherapistProfile
from .models import UserProfile
from .review_access import review_access_valid, requires_email_verification


@override_settings(EMAIL_TWO_STEP_REQUIRED=True, MFA_REQUIRED=False,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class GoogleReviewAccessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            'google-oauth-review', 'google-review@example.com', 'ReviewPassword123!')
        self.practice = Practice.objects.create(name='Fictional review demo', public_booking_slug='google-oauth-review-demo')
        self.profile = UserProfile.objects.create(user=self.user, practice=self.practice, role='therapist')
        self.therapist = TherapistProfile.objects.create(user=self.user, practice=self.practice,
                                                       license_number='FICTIONAL-REVIEW', license_state='DEMO')
        self.config = dict(GOOGLE_REVIEW_USER_ID=str(self.user.pk), GOOGLE_REVIEW_PRACTICE_ID=str(self.practice.pk),
                           GOOGLE_REVIEW_ACCESS_EXPIRES_AT=(timezone.now()+timedelta(days=60)).isoformat())

    def test_real_login_reaches_integrations_without_email_challenge(self):
        with self.settings(**self.config):
            self.assertTrue(review_access_valid(self.user))
            response = self.client.post(reverse('login'), {'username':self.user.email,'password':'ReviewPassword123!'})
            self.assertNotIn('/email/', response.url)
            self.assertEqual(self.client.get(reverse('practice_settings:integrations')).status_code, 200)
            self.assertEqual(self.client.get('/admin/').status_code, 302)
            self.assertRedirects(self.client.get(reverse('email_security_challenge')), '/dashboard/', fetch_redirect_response=False)

    def test_other_user_still_needs_email_code(self):
        other = get_user_model().objects.create_user('ordinary', 'ordinary@example.com', 'Password123!')
        with self.settings(**self.config):
            self.assertTrue(requires_email_verification(other))
            self.client.force_login(other)
            self.assertRedirects(self.client.get('/dashboard/'), reverse('email_security_challenge'), fetch_redirect_response=False)

    def test_configuration_and_tenant_and_role_are_bound(self):
        for key,value in [('GOOGLE_REVIEW_USER_ID','99999'),('GOOGLE_REVIEW_PRACTICE_ID','99999'),
                          ('GOOGLE_REVIEW_ACCESS_EXPIRES_AT',''),('GOOGLE_REVIEW_ACCESS_EXPIRES_AT','not-a-date'),
                          ('GOOGLE_REVIEW_ACCESS_EXPIRES_AT','2026-01-01T00:00:00'),
                          ('GOOGLE_REVIEW_ACCESS_EXPIRES_AT',(timezone.now()-timedelta(seconds=1)).isoformat())]:
            with self.subTest(key=key,value=value), self.settings(**{**self.config,key:value}):
                self.assertFalse(review_access_valid(self.user))
        with self.settings(**self.config):
            for field in ['is_staff','is_superuser']:
                setattr(self.user,field,True)
                self.assertFalse(review_access_valid(self.user))
                setattr(self.user,field,False)
            self.profile.role='owner'
            self.assertFalse(review_access_valid(self.user))
            self.profile.role='therapist'
            self.practice.public_booking_slug='ordinary-practice'
            self.assertFalse(review_access_valid(self.user))

    def test_expiry_revokes_existing_session(self):
        with self.settings(**self.config):
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(reverse('practice_settings:integrations')).status_code,200)
        with self.settings(**{**self.config,'GOOGLE_REVIEW_ACCESS_EXPIRES_AT':(timezone.now()-timedelta(seconds=1)).isoformat()}):
            self.assertEqual(self.client.get('/dashboard/').status_code,403)
            self.assertNotIn('_auth_user_id',self.client.session)

    def test_cannot_read_another_practice_client(self):
        from apps.clients.models import Client
        other = Practice.objects.create(name='Other practice')
        client = Client.objects.create(practice=other,first_name='Other',last_name='Fictional')
        with self.settings(**self.config):
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(f'/clients/{client.pk}/').status_code,404)
