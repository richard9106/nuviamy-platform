import io
import json
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.core.exceptions import PermissionDenied
from django.core.management import call_command, CommandError
from django.test import RequestFactory, SimpleTestCase, TestCase
from apps.accounts.models import UserProfile
from apps.practices.forms import GoogleOAuthSelectionForm
from apps.practices.google_oauth import build_google_authorization_url, google_api_request
from apps.practices.google_policy import CALENDAR_SCOPE, grants_are_approved
from apps.practices.models import ExternalIntegration, Practice, TherapistProfile
from apps.documents.google_drive import drive_request


class ApprovedGoogleScopeTests(SimpleTestCase):
    def test_all_practices_request_only_calendar_even_for_tampered_form_fields(self):
        for pk in [1, 6, 123456]:
            form = GoogleOAuthSelectionForm({'calendar_enabled': 'on', 'send_email_enabled': 'on',
                'read_email_enabled': 'on', 'file_storage_enabled': 'on'}, practice=Practice(pk=pk))
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(form.get_enabled_scopes(), [CALENDAR_SCOPE])
            instance = form.save(commit=False)
            self.assertFalse(instance.send_email_enabled or instance.read_email_enabled or instance.file_storage_enabled)
        self.assertFalse(GoogleOAuthSelectionForm({'send_email_enabled':'on'}).is_valid())

    def test_authorization_builder_refuses_unapproved_scopes(self):
        for scopes in [['https://www.googleapis.com/auth/gmail.send'],
                       [CALENDAR_SCOPE, 'https://www.googleapis.com/auth/calendar.events'], []]:
            with self.assertRaises(PermissionDenied):
                build_google_authorization_url(RequestFactory().get('/'), scopes, 'state')

    def test_api_calls_reject_unapproved_destinations_before_credentials_or_network(self):
        urls = ['https://gmail.googleapis.com/gmail/v1/users/me/messages',
            'https://www.googleapis.com/drive/v3/files',
            'https://www.googleapis.com/upload/drive/v3/files',
            'https://example.com/calendar/v3/calendars/primary/events',
            'http://www.googleapis.com/calendar/v3/calendars/primary/events',
            'https://www.googleapis.com/calendar/v3/calendars/other/events']
        with patch('apps.practices.google_oauth.urlopen') as network:
            for url in urls:
                with self.assertRaises(PermissionDenied): google_api_request(None, url)
            network.assert_not_called()
        with patch('apps.documents.google_drive.urlopen') as network:
            with self.assertRaises(PermissionDenied): drive_request(None, urls[2])
            network.assert_not_called()

    def test_actual_google_email_scope_alias_is_accepted_but_broader_grants_are_not(self):
        self.assertTrue(grants_are_approved(['openid', 'https://www.googleapis.com/auth/userinfo.email', CALENDAR_SCOPE]))
        self.assertFalse(grants_are_approved([CALENDAR_SCOPE, 'https://www.googleapis.com/auth/gmail.send']))
        self.assertFalse(grants_are_approved(['openid', 'email']))


class GoogleApprovalCleanupTests(TestCase):
    def setUp(self):
        practice = Practice.objects.create(name='Approved calendar')
        self.approved = ExternalIntegration.objects.create(practice=practice, provider='google', status='connected',
            calendar_enabled=True, enabled_scopes=[CALENDAR_SCOPE], granted_scopes=['openid','email',CALENDAR_SCOPE],
            access_token='fictional-approved-access', refresh_token='fictional-approved-refresh')
        self.legacy = ExternalIntegration.objects.create(practice=Practice.objects.create(name='Old calendar'),
            provider='google', status='connected', calendar_enabled=True, send_email_enabled=True,
            read_email_enabled=True, file_storage_enabled=True, enabled_scopes=['https://www.googleapis.com/auth/calendar.events'],
            granted_scopes=['https://www.googleapis.com/auth/calendar.events'], access_token='old-access', refresh_token='old-refresh', oauth_state='old-state')
        self.dropbox = ExternalIntegration.objects.create(practice=practice, provider='dropbox', file_storage_enabled=True)
        review_practice = Practice.objects.create(name='Google review', public_booking_slug='google-oauth-review-demo')
        self.reviewer = get_user_model().objects.create_user('google-oauth-review')
        UserProfile.objects.create(user=self.reviewer, practice=review_practice, role='therapist')
        TherapistProfile.objects.create(user=self.reviewer, practice=review_practice)

    def command(self, apply=False):
        output = io.StringIO()
        call_command('finalize_google_verification', apply=apply, stdout=output)
        return json.loads(output.getvalue())

    def test_dry_run_does_not_change_accounts_or_integrations(self):
        result = self.command()
        self.assertFalse(result['applied'])
        self.reviewer.refresh_from_db(); self.legacy.refresh_from_db()
        self.assertTrue(self.reviewer.is_active)
        self.assertEqual(self.legacy.status, 'connected')
        self.assertEqual(self.legacy.refresh_token, 'old-refresh')

    def test_cleanup_preserves_approved_connection_closes_review_access_and_is_idempotent(self):
        result = self.command(apply=True)
        self.assertTrue(result['reviewer_deactivated'])
        self.approved.refresh_from_db(); self.legacy.refresh_from_db(); self.dropbox.refresh_from_db(); self.reviewer.refresh_from_db()
        self.assertEqual(self.approved.status, 'connected')
        self.assertEqual(self.approved.refresh_token, 'fictional-approved-refresh')
        self.assertEqual(self.legacy.status, 'needs_reauth')
        self.assertEqual(self.legacy.enabled_scopes, [CALENDAR_SCOPE])
        self.assertEqual(self.legacy.granted_scopes, [])
        self.assertEqual(self.legacy.refresh_token, '')
        self.assertEqual(self.legacy.oauth_state, '')
        self.assertFalse(self.legacy.send_email_enabled or self.legacy.read_email_enabled or self.legacy.file_storage_enabled)
        self.assertTrue(self.dropbox.file_storage_enabled)
        self.assertFalse(self.reviewer.is_active)
        self.assertIsNone(ModelBackend().get_user(self.reviewer.pk))
        repeat = self.command(apply=True)
        self.assertEqual(repeat['integrations_changed'], 0)
        self.assertFalse(repeat['reviewer_deactivated'])

    def test_command_refuses_misbound_reviewer_before_any_changes(self):
        profile = self.reviewer.nuvia_profile
        profile.role = 'owner'; profile.save()
        with self.assertRaises(CommandError): self.command(apply=True)
        self.legacy.refresh_from_db(); self.reviewer.refresh_from_db()
        self.assertEqual(self.legacy.refresh_token, 'old-refresh')
        self.assertTrue(self.reviewer.is_active)
