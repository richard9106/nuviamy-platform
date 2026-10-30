from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import transaction, connection, close_old_connections
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.audit.testing import ProtectedRecordsTransactionTestCase
from apps.accounts.models import UserProfile
from apps.billing.models import PracticeSubscription
from apps.clients.models import Client
from apps.portal.models import ClientPortalAccess, ClientPortalRequest
from apps.practices.models import Practice, TherapistProfile
from .models import Appointment, SessionEmailNotification as Alert
from .notifications import deliver_session_email, queue_session_email


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   MFA_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False)
class SessionNotificationTests(TestCase):
    def setUp(self):
        self.practice = Practice.objects.create(name='Synthetic practice')
        self.staff = get_user_model().objects.create_user('notice-fixture', email='staff@example.invalid')
        self.profile = UserProfile.objects.create(user=self.staff, practice=self.practice, role='therapist')
        self.therapist = TherapistProfile.objects.create(user=self.staff, practice=self.practice)
        self.patient = Client.objects.create(practice=self.practice, first_name='ConfidentialFixture', last_name='Patient')
        self.start = timezone.now() + timedelta(days=2)

    def appointment(self, **kwargs):
        return Appointment.objects.create(**(dict(practice=self.practice, client=self.patient, therapist=self.therapist,
            starts_at=self.start, ends_at=self.start+timedelta(minutes=50)) | kwargs))

    def enable(self, sessions=True, requests=True):
        self.profile.session_email_notifications = sessions
        self.profile.request_email_notifications = requests
        self.profile.save()

    def request(self, appointment, **kwargs):
        return ClientPortalRequest.objects.create(**(dict(practice=self.practice, client=self.patient,
            appointment=appointment, category='cancellation', subject='Confidential subject', message='Private clinical content') | kwargs))

    def test_default_opt_out_produces_no_outbox_or_email(self):
        with self.captureOnCommitCallbacks(execute=True):
            appt = self.appointment()
            self.request(appt)
        self.assertFalse(Alert.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_scheduled_changed_and_cancelled_each_send_once_without_google(self):
        self.enable()
        with self.captureOnCommitCallbacks(execute=True):
            appt = self.appointment()
        with self.captureOnCommitCallbacks(execute=True):
            appt.starts_at += timedelta(hours=1); appt.ends_at += timedelta(hours=1); appt.save()
        with self.captureOnCommitCallbacks(execute=True):
            appt.status = 'cancelled'; appt.save(update_fields=['status'])
        self.assertEqual(list(Alert.objects.values_list('kind', flat=True)), ['created','updated','cancelled'])
        self.assertEqual(len(mail.outbox), 3)
        for email in mail.outbox:
            self.assertEqual(email.to, ['staff@example.invalid'])
            self.assertNotIn(self.patient.first_name, email.body)
            self.assertNotIn(self.start.isoformat(), email.body)
            self.assertIn('https://nuviamy.com/appointments/', email.body)
            self.assertEqual(email.alternatives[0].mimetype, 'text/html')
        self.assertFalse(deliver_session_email(Alert.objects.first().pk))
        self.assertEqual(len(mail.outbox), 3)

    def test_note_and_sync_saves_do_not_send_updates(self):
        self.enable()
        appt = self.appointment()
        Alert.objects.all().delete()
        with self.captureOnCommitCallbacks(execute=True):
            appt.notes = 'Private note'; appt.save()
            appt.starts_at += timedelta(hours=1)
            appt.sync_error = 'Provider failed'; appt.save(update_fields=['sync_error'])
        self.assertFalse(Alert.objects.exists())

    def test_request_is_not_a_cancellation_and_free_text_stays_private(self):
        self.enable(sessions=False)
        appt = self.appointment()
        with self.captureOnCommitCallbacks(execute=True):
            request = self.request(appt)
        appt.refresh_from_db()
        self.assertEqual(appt.status, 'scheduled')
        self.assertEqual(Alert.objects.get().kind, 'cancellation_request')
        self.assertIn('has not been changed automatically', mail.outbox[0].body)
        for private in (request.subject, request.message, self.patient.first_name):
            self.assertNotIn(private, mail.outbox[0].body + mail.outbox[0].alternatives[0].content)
        with self.captureOnCommitCallbacks(execute=True):
            request.status = 'reviewed'; request.save()
            queue_session_email(appt, 'cancellation_request', portal_request=request)
        self.assertEqual(len(mail.outbox), 1)

    def test_reschedule_request_sends_only_request_preference(self):
        self.enable(sessions=False)
        with self.captureOnCommitCallbacks(execute=True):
            appt = self.appointment()
            self.request(appt, category='reschedule')
        self.assertEqual(Alert.objects.get().kind, 'reschedule_request')
        self.assertEqual(len(mail.outbox), 1)

    def test_rollback_never_sends_or_retains_outbox(self):
        self.enable()
        with self.captureOnCommitCallbacks(execute=True):
            try:
                with transaction.atomic():
                    self.appointment()
                    raise RuntimeError('simulated rollback')
            except RuntimeError:
                pass
        self.assertFalse(Alert.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_retry_survives_provider_error_and_does_not_store_error_details(self):
        self.enable()
        with patch('apps.appointments.notifications.send_mail', side_effect=OSError('secret@invalid private')):
            with self.captureOnCommitCallbacks(execute=True):
                self.appointment()
        alert = Alert.objects.get()
        self.assertEqual((alert.state, alert.attempts), ('pending',1))
        self.assertFalse(deliver_session_email(alert.pk))  # Respect backoff.
        Alert.objects.update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        call_command('send_session_notifications', stdout=StringIO())
        alert.refresh_from_db()
        self.assertEqual((alert.state, alert.attempts), ('sent',2))
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn('secret@invalid', str(alert.__dict__))

    def test_retries_are_bounded(self):
        self.enable()
        self.appointment()
        alert = Alert.objects.get()
        with patch('apps.appointments.notifications.send_mail', return_value=0):
            for _ in range(5):
                Alert.objects.update(next_attempt_at=timezone.now()-timedelta(seconds=1))
                deliver_session_email(alert.pk)
        alert.refresh_from_db()
        self.assertEqual((alert.state, alert.attempts), ('failed',5))
        self.assertFalse(deliver_session_email(alert.pk))

    def test_pending_delivery_rechecks_opt_out_and_current_assignment(self):
        self.enable()
        self.appointment()
        self.enable(sessions=False)
        alert = Alert.objects.get()
        self.assertFalse(deliver_session_email(alert.pk))
        alert.refresh_from_db(); self.assertEqual(alert.state,'skipped')
        self.enable()
        appt = self.appointment()
        alert = Alert.objects.order_by('pk').last()
        other = get_user_model().objects.create_user('other-fixture', email='other@example.invalid')
        therapist = TherapistProfile.objects.create(user=other, practice=self.practice, license_number='OTHER')
        Appointment.objects.filter(pk=appt.pk).update(therapist=therapist)
        self.assertFalse(deliver_session_email(alert.pk))
        self.assertEqual(len(mail.outbox), 0)

    def test_inactive_wrong_practice_client_and_permission_revocation_do_not_send(self):
        self.enable()
        for change in ('inactive','practice','client','permission'):
            with self.subTest(change=change):
                appt = self.appointment()
                alert = Alert.objects.order_by('pk').last()
                if change=='inactive':
                    self.staff.is_active=False; self.staff.save()
                elif change=='practice':
                    self.profile.practice=Practice.objects.create(name='Other practice'); self.profile.save()
                elif change=='client':
                    self.profile.role='client'; self.profile.save()
                else:
                    self.profile.permissions={'appointments': {'view':False}}; self.profile.save()
                self.assertFalse(deliver_session_email(alert.pk))
                self.staff.is_active=True; self.staff.save()
                self.profile.practice=self.practice; self.profile.role='therapist'; self.profile.permissions={}; self.profile.save()
        self.assertEqual(len(mail.outbox),0)

    def test_resolved_or_expired_requests_are_not_sent(self):
        self.enable(sessions=False)
        appt = self.appointment()
        request = self.request(appt)
        request.status='resolved'; request.save()
        self.assertFalse(deliver_session_email(Alert.objects.get().pk))
        self.enable()
        self.appointment()
        alert = Alert.objects.order_by('pk').last()
        Alert.objects.filter(pk=alert.pk).update(created_at=timezone.now()-timedelta(days=2))
        self.assertFalse(deliver_session_email(alert.pk))

    def test_only_own_preferences_can_be_updated_even_after_subscription_ends(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('profile_settings'))
        self.assertContains(response,'Save email preferences')
        self.practice.subscription_required=True; self.practice.save()
        PracticeSubscription.objects.create(practice=self.practice,status='canceled')
        response = self.client.post(reverse('notification_preferences'), {
            'session_email_notifications':'on','request_email_notifications':'on','user_id':'999999'})
        self.assertRedirects(response, reverse('profile_settings'), fetch_redirect_response=False)
        self.profile.refresh_from_db()
        self.assertTrue(self.profile.session_email_notifications)
        self.assertTrue(self.profile.request_email_notifications)
        response = self.client.post(reverse('notification_preferences'), {})
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.request_email_notifications)

    def test_client_cannot_enable_staff_alerts_and_get_cannot_modify(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('notification_preferences')).status_code,405)
        self.profile.role='client'; self.profile.save()
        response = self.client.post(reverse('notification_preferences'), {'session_email_notifications':'on'})
        self.assertEqual(response.status_code,403)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.session_email_notifications)




@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row-lock concurrency check')
@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class NotificationWorkerConcurrencyTests(ProtectedRecordsTransactionTestCase):
    def test_two_workers_only_submit_one_email(self):
        practice = Practice.objects.create(name='Concurrent synthetic practice')
        user = get_user_model().objects.create_user('concurrent-notice', email='concurrent@example.invalid')
        profile = UserProfile.objects.create(user=user, practice=practice, role='therapist')
        therapist = TherapistProfile.objects.create(user=user, practice=practice)
        patient = Client.objects.create(practice=practice,first_name='Synthetic',last_name='Fixture')
        start = timezone.now()+timedelta(days=1)
        appointment = Appointment.objects.create(practice=practice,therapist=therapist,client=patient,
            starts_at=start, ends_at=start+timedelta(minutes=50))
        profile.session_email_notifications=True; profile.save()
        alert = Alert.objects.create(event_key='concurrency-fixture',practice=practice,recipient=user,
            appointment=appointment,kind='created')
        barrier = Barrier(2)
        def worker():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return deliver_session_email(alert.pk)
            finally:
                close_old_connections()
        with patch('apps.appointments.notifications.send_mail',return_value=1) as provider:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _:worker(),range(2)))
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(provider.call_count,1)
        alert.refresh_from_db()
        self.assertEqual((alert.state,alert.attempts),('sent',1))
