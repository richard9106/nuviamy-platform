from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import Client as HttpClient, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import AccountSecurity, UserProfile
from apps.appointments.models import Appointment, SessionEmailNotification
from apps.audit.models import AuditLog
from apps.billing.models import PracticeSubscription
from apps.clients.models import Client
from apps.portal.models import ClientPortalAccess
from apps.practices.founding_offer import offer_for
from apps.practices.models import FoundingTherapistInvitation, Practice, TherapistProfile
from .models import SupportTicket

KEY = 'MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA='


@override_settings(FIELD_ENCRYPTION_KEY=KEY, MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=False,
                   EMAIL_TWO_STEP_REQUIRED=False,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class PlatformOperationsTests(TestCase):
    pages = ('staff_overview', 'staff_practices', 'staff_users', 'staff_offers',
             'staff_subscriptions', 'staff_notifications', 'staff_contracts', 'staff_activity')

    def setUp(self):
        self.operator = get_user_model().objects.create_superuser('ops-fixture', 'ops@example.invalid', 'LocalFixture123!')
        self.practice = Practice.objects.create(name='Synthetic Practice', email='practice@example.invalid')
        self.owner = get_user_model().objects.create_user('owner-fixture', email='owner@example.invalid')
        UserProfile.objects.create(user=self.owner, practice=self.practice, role='owner')
        self.patient = Client.objects.create(practice=self.practice, first_name='PrivatePatient', last_name='Fixture')
        self.patient_user = get_user_model().objects.create_user('patient-fixture', email='privatepatient@example.invalid')
        ClientPortalAccess.objects.create(user=self.patient_user, practice=self.practice, client=self.patient)
        self.client.force_login(self.operator)

    def test_pages_render_without_clinical_data_and_are_not_cached(self):
        for name in self.pages:
            with self.subTest(page=name):
                response = self.client.get(reverse(name))
                self.assertEqual(response.status_code, 200)
                self.assertIn('no-store', response['Cache-Control'])
                self.assertContains(response, 'noindex, nofollow')
                self.assertNotContains(response, 'PrivatePatient')
                self.assertNotContains(response, self.patient_user.email)
                self.assertTrue(AuditLog.objects.filter(object_type='access.' + name).exists())
        self.assertContains(self.client.get(reverse('staff_practice_detail', args=[self.practice.pk])), self.owner.email)

    def test_ordinary_and_staff_users_cannot_access_platform(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse('staff_overview')).status_code, 302)
        for staff in (False, True):
            self.owner.is_staff = staff
            self.owner.save(update_fields=['is_staff'])
            self.client.force_login(self.owner)
            for name in self.pages:
                self.assertEqual(self.client.get(reverse(name)).status_code, 403)
            self.assertEqual(self.client.post(reverse('staff_offers'), {'email': 'intrusion@example.invalid'}).status_code, 403)
            self.assertEqual(self.client.post(reverse('staff_user_action', args=[self.operator.pk]), {'action': 'revoke'}).status_code, 403)
        self.assertFalse(FoundingTherapistInvitation.objects.exclude(email='').exists())

    @override_settings(MFA_PRIVILEGED_REQUIRED=True)
    def test_mfa_is_required_for_platform(self):
        self.assertRedirects(self.client.get(reverse('staff_overview')), reverse('mfa_setup'), fetch_redirect_response=False)

    def test_stale_authentication_blocks_writes(self):
        session = self.client.session
        session['security_auth_at'] = 0
        session.save()
        response = self.client.post(reverse('staff_offers'), {'email': 'stale@example.invalid'})
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('security_reauthenticate'), response.url)
        self.assertFalse(FoundingTherapistInvitation.objects.exclude(email='').exists())

    def test_search_and_pagination_preserve_filters(self):
        other = Practice.objects.create(name='Other business')
        page = self.client.get(reverse('staff_practices'), {'q': self.owner.email})
        self.assertContains(page, self.practice.name)
        self.assertNotContains(page, other.name)
        page = self.client.get(reverse('staff_users'), {'q': 'missing'})
        self.assertNotContains(page, self.owner.email)
        Practice.objects.bulk_create([Practice(name=f'Bulk {i}', public_booking_slug=f'bulk-{i}') for i in range(23)])
        page = self.client.get(reverse('staff_practices'), {'q': 'Bulk'})
        self.assertContains(page, 'q=Bulk')
        self.assertContains(page, 'Next')
        self.assertEqual(len(page.context['practices']), 20)

    def test_issue_rotate_and_redeemed_offer_guards_use_existing_workflow(self):
        url = reverse('staff_offers')
        response = self.client.post(url, {'email': self.owner.email})
        self.assertEqual(response.status_code, 200)
        issued = response.context['issued']
        invitation = offer_for(issued['code'], self.owner.email)
        self.assertEqual(invitation.slot, issued['slot'])
        self.assertFalse(mail.outbox)
        self.assertNotContains(self.client.get(url), issued['code'])
        self.assertNotIn(issued['code'], str(dict(self.client.session)))
        self.assertNotIn(issued['code'], str(list(AuditLog.objects.values_list('metadata', flat=True))))
        self.assertContains(self.client.post(url, {'email': self.owner.email}), 'already has a code')
        rotated = self.client.post(url, {'email': self.owner.email, 'rotate': 'on'}).context['issued']
        self.assertNotEqual(rotated['code'], issued['code'])
        invitation.refresh_from_db()
        invitation.redeemed_at = timezone.now()
        invitation.save(update_fields=['redeemed_at'])
        self.assertContains(self.client.post(url, {'email': self.owner.email, 'rotate': 'on'}), 'already has a code')

    def test_application_prefills_email_and_invalid_reference_is_safe(self):
        ticket = SupportTicket.objects.create(contact_email=self.owner.email, topic='early_access')
        page = self.client.get(reverse('staff_offers'), {'application': ticket.pk})
        self.assertEqual(page.context['form'].initial['email'], self.owner.email)
        self.assertEqual(self.client.get(reverse('staff_offers'), {'application': 'invalid'}).status_code, 200)

    def test_session_revocation_blocks_patient_and_privileged_targets(self):
        state, _ = AccountSecurity.objects.get_or_create(user=self.owner)
        previous = state.session_version
        url = reverse('staff_user_action', args=[self.owner.pk])
        self.assertRedirects(self.client.post(url, {'action': 'revoke'}), reverse('staff_users'))
        state.refresh_from_db()
        self.assertNotEqual(state.session_version, previous)
        self.assertEqual(self.client.post(reverse('staff_user_action', args=[self.patient_user.pk]), {'action': 'revoke'}).status_code, 404)
        state, _ = AccountSecurity.objects.get_or_create(user=self.operator)
        previous = state.session_version
        self.client.post(reverse('staff_user_action', args=[self.operator.pk]), {'action': 'revoke'})
        state.refresh_from_db()
        self.assertEqual(state.session_version, previous)

    @patch('apps.dashboard.platform_views.send_account_access_email', return_value=True)
    def test_access_email_is_only_sent_by_explicit_post(self, send):
        self.client.get(reverse('staff_users'))
        send.assert_not_called()
        self.client.post(reverse('staff_user_action', args=[self.owner.pk]), {'action': 'resend'})
        self.assertEqual(send.call_args.args[1], self.owner)
        send.assert_called_once()
        self.assertTrue(AuditLog.objects.filter(metadata__event='platform_access_email_sent').exists())

    def test_post_actions_require_csrf(self):
        client = HttpClient(enforce_csrf_checks=True)
        client.force_login(self.operator)
        self.assertEqual(client.post(reverse('staff_offers'), {'email': self.owner.email}).status_code, 403)
        self.assertEqual(client.post(reverse('staff_user_action', args=[self.owner.pk]), {'action': 'revoke'}).status_code, 403)
        self.assertEqual(client.post(reverse('staff_notifications'), {'notification': 1, 'action': 'retry'}).status_code, 403)

    def test_subscription_view_uses_actual_access_and_cannot_change_stripe(self):
        self.practice.subscription_required = True
        self.practice.free_trial_ends_at = timezone.now() - timedelta(days=1)
        self.practice.save()
        subscription = PracticeSubscription.objects.create(practice=self.practice, plan='solo', billing_period='monthly', status='past_due')
        page = self.client.get(reverse('staff_subscriptions'), {'status': 'past_due'})
        self.assertContains(page, 'Past Due')
        self.assertEqual(page.context['practices'][0].access_state['mode'], 'readonly')
        self.assertEqual(self.client.post(reverse('staff_subscriptions'), {'status': 'active'}).status_code, 405)
        subscription.refresh_from_db()
        self.assertEqual(subscription.status, 'past_due')

    @patch('apps.dashboard.platform_views.deliver_session_email')
    def test_only_recent_failed_alerts_can_be_retried_once(self, deliver):
        therapist = TherapistProfile.objects.create(user=self.owner, practice=self.practice)
        start = timezone.now() + timedelta(days=1)
        appointment = Appointment.objects.create(practice=self.practice, client=self.patient, therapist=therapist,
            starts_at=start, ends_at=start + timedelta(minutes=50))
        alert = SessionEmailNotification.objects.create(practice=self.practice, recipient=self.owner,
            appointment=appointment, event_key='synthetic-retry-fixture', kind='created', state='failed', attempts=5)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('staff_notifications'), {'action': 'retry', 'notification': alert.pk})
        self.assertRedirects(response, reverse('staff_notifications'))
        deliver.assert_called_once_with(alert.pk)
        alert.refresh_from_db()
        self.assertEqual((alert.state, alert.attempts), ('pending', 0))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('staff_notifications'), {'action': 'retry', 'notification': alert.pk})
        deliver.assert_called_once()
        SessionEmailNotification.objects.filter(pk=alert.pk).update(state='failed', created_at=timezone.now() - timedelta(days=2))
        with self.captureOnCommitCallbacks(execute=True):
            self.client.post(reverse('staff_notifications'), {'action': 'retry', 'notification': alert.pk})
        deliver.assert_called_once()
        self.assertNotContains(self.client.get(reverse('staff_notifications')), self.patient.first_name)

    def test_reauthentication_returns_to_user_list_for_post_only_action(self):
        session = self.client.session
        session['security_auth_at'] = 0
        session.save()
        response = self.client.post(reverse('staff_user_action', args=[self.owner.pk]), {'action': 'revoke'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(parse_qs(urlsplit(response.url).query)['next'], [reverse('staff_users')])
        self.assertFalse(AuditLog.objects.filter(metadata__event='platform_sessions_revoked').exists())

    def test_expired_personal_practice_does_not_block_platform_operations(self):
        self.practice.subscription_required = True
        self.practice.free_trial_ends_at = timezone.now() - timedelta(days=1)
        self.practice.save()
        UserProfile.objects.create(user=self.operator, practice=self.practice, role='admin')
        self.assertEqual(self.client.get(reverse('staff_overview')).status_code, 200)
        self.assertContains(self.client.post(reverse('staff_offers'), {'email': 'expired-fixture@example.invalid'}),
                            'Six-month offer created')

    def test_contract_status_uses_current_version_without_exposing_snapshot(self):
        from apps.accounts.models import StandardAgreementAcceptance
        from apps.accounts.standard_agreements import AGREEMENT_VERSION, digest
        snapshot = {'synthetic': 'PrivateStoredContract'}
        StandardAgreementAcceptance.objects.create(practice=self.practice, signer=self.owner,
            version=AGREEMENT_VERSION, snapshot=snapshot, digest=digest(snapshot))
        response = self.client.get(reverse('staff_contracts'))
        self.assertTrue(response.context['practices'][0].current_agreement)
        self.assertContains(response, 'Accepted')
        self.assertNotContains(response, 'PrivateStoredContract')

    def test_offer_audit_references_primary_key_when_slot_differs(self):
        FoundingTherapistInvitation.objects.filter(slot=1).update(id=100)
        response = self.client.post(reverse('staff_offers'), {'email': self.owner.email})
        self.assertEqual(response.context['issued']['slot'], 1)
        event = AuditLog.objects.get(metadata__event='platform_offer_issued')
        self.assertEqual(event.object_id, '100')
