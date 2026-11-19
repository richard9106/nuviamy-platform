from datetime import timedelta
from unittest.mock import patch

from django.test import Client as HttpClient, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from .models import Appointment, PracticeAvailabilityOverride


@override_settings(MFA_REQUIRED=False)
class CalendarDragTests(TestCase):
    def setUp(self):
        from .tests import AppointmentViewTests
        self.user, self.practice, self.therapist, self.patient = AppointmentViewTests.create_practice_user(self)
        self.start = timezone.localtime().replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=1)
        self.appointment = Appointment.objects.create(practice=self.practice, therapist=self.therapist, client=self.patient,
            starts_at=self.start, ends_at=self.start + timedelta(minutes=80))
        self.url = reverse('appointments:reschedule', args=[self.appointment.pk])
        self.data = {'date': self.start.date().isoformat(), 'time': '13:00',
            'expected_starts_at': self.appointment.starts_at.isoformat(), 'expected_ends_at': self.appointment.ends_at.isoformat()}
        self.headers = {'HTTP_X_REQUESTED_WITH': 'XMLHttpRequest'}
        self.client.force_login(self.user)

    def test_move_returns_json_and_preserves_duration_and_client(self):
        with patch('apps.appointments.views.sync_appointment_to_google') as sync:
            response = self.client.post(self.url, self.data, **self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['ok'])
        self.appointment.refresh_from_db()
        self.assertEqual(timezone.localtime(self.appointment.starts_at).hour, 13)
        self.assertEqual(self.appointment.duration_minutes, 80)
        self.assertEqual(self.appointment.client, self.patient)
        self.assertEqual(self.appointment.status, Appointment.Status.SCHEDULED)
        sync.assert_called_once()
        self.assertTrue(self.practice.audit_logs.filter(metadata__calendar_drag=True).exists())

    def test_invalid_unavailable_and_conflicting_moves_are_not_saved(self):
        PracticeAvailabilityOverride.objects.create(practice=self.practice, date=self.start.date(), starts_at='14:00', ends_at='15:00', is_available=False)
        Appointment.objects.create(practice=self.practice, therapist=self.therapist, client=self.patient,
            starts_at=self.start.replace(hour=16), ends_at=self.start.replace(hour=17))
        for time in ('bad', '14:00', '16:00'):
            with self.subTest(time=time), patch('apps.appointments.views.sync_appointment_to_google') as sync:
                response = self.client.post(self.url, {**self.data, 'time': time}, **self.headers)
                self.assertEqual(response.status_code, 400)
                self.assertFalse(response.json()['ok'])
                self.appointment.refresh_from_db()
                self.assertEqual(self.appointment.starts_at, self.start)
                sync.assert_not_called()

    def test_stale_calendar_does_not_overwrite_newer_schedule(self):
        self.appointment.starts_at += timedelta(minutes=15)
        self.appointment.ends_at += timedelta(minutes=15)
        self.appointment.save()
        response = self.client.post(self.url, self.data, **self.headers)
        self.assertEqual(response.status_code, 409)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.starts_at, self.start+timedelta(minutes=15))

    def test_inline_move_keeps_permissions_scoping_and_csrf(self):
        csrf_client = HttpClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.url, self.data, **self.headers).status_code, 403)
        from .tests import AppointmentViewTests
        other, _, _, _ = AppointmentViewTests.create_practice_user(self, username='other-drag')
        self.client.force_login(other)
        self.assertEqual(self.client.post(self.url, self.data, **self.headers).status_code, 404)
        profile = self.user.nuvia_profile
        profile.role = UserProfile.Role.THERAPIST
        profile.permissions = {'appointments': {'view': True}}
        profile.save()
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, self.data, **self.headers).status_code, 302)
        self.appointment.refresh_from_db()
        self.assertEqual(self.appointment.starts_at, self.start)
