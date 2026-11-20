from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Appointment, PracticeAvailabilityOverride
from .recurrence import weekly_starts


class WeeklyPlanTests(SimpleTestCase):
    def test_multiple_days_interval_and_inclusive_end(self):
        start = datetime(2026, 11, 16, 10, tzinfo=dt_timezone.utc)
        with timezone.override('UTC'):
            starts = weekly_starts(start, weekdays=[0, 2], interval=2, count=5)
            self.assertEqual([s.date().isoformat() for s in starts], ['2026-11-16', '2026-11-18', '2026-11-30', '2026-12-02', '2026-12-14'])
            starts = weekly_starts(start, weekdays=[0, 2], until=datetime(2026, 12, 2).date())
            self.assertEqual(len(starts), 6)
            self.assertEqual(starts[-1].date().isoformat(), '2026-12-02')

    def test_first_day_selection_and_limit(self):
        start = datetime(2026, 11, 16, 10, tzinfo=dt_timezone.utc)
        with timezone.override('UTC'):
            for options in ({'weekdays': [1], 'count': 4}, {'weekdays': [], 'count': 4}, {'interval': 0, 'count': 4}, {'count': 53}, {'until': datetime(2026, 11, 15).date()}, {'until': datetime(2029, 1, 1).date()}):
                with self.subTest(options=options), self.assertRaises(ValidationError):
                    weekly_starts(start, **options)

    def test_local_hour_survives_dst_and_missing_hour_is_rejected(self):
        zone = ZoneInfo('America/New_York')
        with timezone.override(zone):
            start = datetime(2027, 3, 7, 9, tzinfo=zone)
            starts = weekly_starts(start, count=3)
            self.assertEqual([s.hour for s in starts], [9, 9, 9])
            self.assertEqual([s.utcoffset() for s in starts], [timedelta(hours=-5), timedelta(hours=-4), timedelta(hours=-4)])
            with self.assertRaises(ValidationError):
                weekly_starts(start.replace(hour=2, minute=30), count=3)
            with self.assertRaises(ValidationError):
                weekly_starts(datetime(2027, 10, 31, 1, 30, tzinfo=zone), count=3)


@override_settings(MFA_REQUIRED=False)
class RecurrenceCreationTests(TestCase):
    def setUp(self):
        from .tests import AppointmentViewTests
        self.user, self.practice, self.therapist, self.patient = AppointmentViewTests.create_practice_user(self)
        self.client.force_login(self.user)
        self.data = {'client': self.patient.pk, 'therapist': self.therapist.pk,
            'starts_at': '2026-11-16T10:00', 'ends_at': '2026-11-16T10:50', 'status': 'scheduled', 'appointment_type': 'video',
            'recurrence_rule': 'weekly', 'recurrence_interval': 2, 'recurrence_weekdays': ['0', '2'], 'recurrence_ends': 'count', 'repeat_weekly_count': 5}

    def test_multiple_day_creation_and_date_end(self):
        with timezone.override('UTC'), patch('apps.appointments.views.sync_appointment_to_google') as sync:
            response = self.client.post(reverse('appointments:create'), self.data)
            self.assertEqual(response.status_code, 302)
            sessions = list(Appointment.objects.order_by('starts_at'))
            self.assertEqual([s.starts_at.date().isoformat() for s in sessions], ['2026-11-16', '2026-11-18', '2026-11-30', '2026-12-02', '2026-12-14'])
            self.assertEqual(len({s.series_id for s in sessions}), 1)
            self.assertIsNotNone(sessions[0].series_id)
            self.assertTrue(all(s.duration_minutes == 50 for s in sessions))
            self.assertEqual(sync.call_count, 5)
            from apps.billing.models import Invoice, Payment
            self.assertEqual(Invoice.objects.count(), 0)
            self.assertEqual(Payment.objects.count(), 0)
        # A second series ends inclusively on its last selected date.
        with timezone.override('UTC'):
            response = self.client.post(reverse('appointments:create'), {**self.data, 'starts_at': '2027-01-04T10:00', 'ends_at': '2027-01-04T10:50', 'recurrence_ends': 'date', 'recurrence_until': '2027-01-18'})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(Appointment.objects.filter(starts_at__year=2027).count(), 3)

    def test_conflict_rolls_back_the_entire_new_series(self):
        with timezone.override('UTC'):
            PracticeAvailabilityOverride.objects.create(practice=self.practice, date=datetime(2026, 11, 30).date(), is_available=False)
            with patch('apps.appointments.views.sync_appointment_to_google') as sync:
                response = self.client.post(reverse('appointments:create'), self.data)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(Appointment.objects.count(), 0)
            sync.assert_not_called()
            self.assertContains(response, 'could not be scheduled')
            self.assertEqual(response.context['form']['recurrence_weekdays'].value(), ['0', '2'])

    def test_no_repeat_overrides_stale_count_and_missing_days_are_errors(self):
        with timezone.override('UTC'):
            response = self.client.post(reverse('appointments:create'), {**self.data, 'recurrence_weekdays': []})
            self.assertEqual(response.status_code, 200)
            self.assertIn('recurrence_weekdays', response.context['form'].errors)
            response = self.client.post(reverse('appointments:create'), {**self.data, 'recurrence_rule': 'none', 'repeat_weekly_count': 0})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(Appointment.objects.count(), 1)
            self.assertIsNone(Appointment.objects.get().series_id)

    def test_series_length_is_rejected_before_any_save(self):
        with timezone.override('UTC'):
            response = self.client.post(reverse('appointments:create'), {**self.data, 'recurrence_ends': 'date', 'recurrence_until': '2030-01-01'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertContains(response, 'more than 52 sessions')

    def test_editing_one_session_does_not_regenerate_the_series(self):
        with timezone.override('UTC'):
            self.client.post(reverse('appointments:create'), self.data)
            first = Appointment.objects.order_by('starts_at').first()
            series = first.series_id
            response = self.client.post(reverse('appointments:edit', args=[first.pk]), {
                **self.data, 'starts_at': '2026-11-16T11:00', 'ends_at': '2026-11-16T11:50'})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Appointment.objects.count(), 5)
        first.refresh_from_db()
        self.assertEqual(first.series_id, series)
        self.assertEqual(timezone.localtime(first.starts_at, dt_timezone.utc).hour, 11)
