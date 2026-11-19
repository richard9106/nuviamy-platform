from datetime import timedelta

from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from .models import Appointment, CalendarEvent, PracticeAvailabilityOverride


@override_settings(MFA_REQUIRED=False)
class CalendarEventTests(TestCase):
    def create_practice_user(self, **kwargs):
        from .tests import AppointmentViewTests
        return AppointmentViewTests.create_practice_user(self, **kwargs)

    def setUp(self):
        self.user, self.practice, self.therapist, self.patient = self.create_practice_user()
        self.other_user, self.other_practice, self.other_therapist, _ = self.create_practice_user(username='other-event')
        self.start = timezone.localtime().replace(hour=11, minute=0, second=0, microsecond=0) + timedelta(days=2)
        self.data = {'title': 'Team meeting', 'therapist': self.therapist.pk,
            'starts_at': self.start.strftime('%Y-%m-%dT%H:%M'),
            'ends_at': (self.start+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
            'next': '/appointments/?view=week'}
        self.client.force_login(self.user)

    def test_event_create_update_delete_and_all_calendar_views(self):
        response = self.client.post(reverse('appointments:event_create'), self.data)
        self.assertEqual(response.url, self.data['next'])
        event = CalendarEvent.objects.get()
        self.assertEqual(event.practice, self.practice)
        self.assertEqual(Appointment.objects.count(), 0)
        self.assertEqual(PracticeAvailabilityOverride.objects.count(), 0)
        for view in ('day', 'week', 'month', 'agenda'):
            with self.subTest(view=view):
                response = self.client.get(reverse('appointments:list'), {'view': view, 'date': self.start.date().isoformat(), 'month': self.start.strftime('%Y-%m')})
                self.assertContains(response, 'Team meeting')
        url = reverse('appointments:event_edit', args=[event.pk])
        self.assertContains(self.client.get(url), 'Team meeting')
        self.client.post(url, {**self.data, 'title': 'Updated meeting'})
        event.refresh_from_db()
        self.assertEqual(event.title, 'Updated meeting')
        self.assertTrue(self.practice.audit_logs.filter(object_type='CalendarEvent', action='update').exists())
        self.assertEqual(self.client.get(reverse('appointments:event_delete', args=[event.pk])).status_code, 405)
        self.client.post(reverse('appointments:event_delete', args=[event.pk]))
        self.assertFalse(CalendarEvent.objects.exists())

    def test_scope_invalid_times_and_redirect_validation(self):
        for changes in ({'therapist': self.other_therapist.pk}, {'ends_at': self.data['starts_at']}, {'ends_at': (self.start+timedelta(days=1)).strftime('%Y-%m-%dT%H:%M')}):
            response = self.client.post(reverse('appointments:event_create'), {**self.data, **changes})
            self.assertEqual(response.status_code, 200)
            self.assertFalse(CalendarEvent.objects.exists())
        response = self.client.post(reverse('appointments:event_create'), {**self.data, 'next': 'https://example.com'})
        self.assertEqual(response.url, reverse('appointments:list'))
        event = CalendarEvent.objects.get()
        self.client.force_login(self.other_user)
        response = self.client.get(reverse('appointments:event_edit', args=[event.pk]))
        self.assertEqual(response.status_code, 404, getattr(response, 'url', ''))
        self.assertEqual(self.client.post(reverse('appointments:event_delete', args=[event.pk])).status_code, 404)
        self.assertNotContains(self.client.get(reverse('appointments:list'), {'view': 'agenda', 'date': self.start.date().isoformat()}), event.title)

    def test_therapist_cannot_read_another_therapists_event(self):
        event = CalendarEvent.objects.create(practice=self.practice, therapist=self.therapist, title='Private admin meeting', starts_at=self.start, ends_at=self.start+timedelta(hours=1))
        profile = self.other_user.nuvia_profile
        profile.practice = self.practice
        profile.permissions = {'appointments': {'view': True, 'create': True, 'edit': True}}
        profile.role = UserProfile.Role.THERAPIST
        profile.save()
        self.other_therapist.practice = self.practice
        self.other_therapist.save()
        self.client.force_login(self.other_user)
        response = self.client.get(reverse('appointments:event_edit', args=[event.pk]))
        self.assertEqual(response.status_code, 404, getattr(response, 'url', ''))
        self.assertEqual(self.client.post(reverse('appointments:event_create'), self.data).status_code, 200)
        self.assertEqual(CalendarEvent.objects.count(), 1)

    def test_out_of_office_keeps_existing_hours_and_other_blocks(self):
        original = PracticeAvailabilityOverride.objects.create(practice=self.practice, date=self.start.date(), starts_at='09:00', ends_at='17:00', is_available=True)
        blocked = PracticeAvailabilityOverride.objects.create(practice=self.practice, date=self.start.date(), starts_at='10:00', ends_at='11:00', is_available=False)
        data = {'date': self.start.date().isoformat(), 'starts_at': '14:00', 'ends_at': '15:00', 'calendar_entry_mode': 'out-of-office'}
        response = self.client.post(reverse('appointments:availability_create'), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(PracticeAvailabilityOverride.objects.filter(pk=original.pk).exists())
        self.assertTrue(PracticeAvailabilityOverride.objects.filter(pk=blocked.pk).exists())
        self.assertEqual(self.practice.availability_overrides.count(), 3)
        self.client.post(reverse('appointments:availability_create'), {**data, 'calendar_entry_mode': 'availability', 'is_available': 'on', 'starts_at': '08:00', 'ends_at': '18:00'})
        self.assertEqual(self.practice.availability_overrides.filter(is_available=False).count(), 2)
        self.assertEqual(self.practice.availability_overrides.filter(is_available=True).count(), 1)

    def test_overlapping_event_and_appointment_get_separate_lanes(self):
        from .views import AppointmentListView
        appointment = Appointment(practice=self.practice, therapist=self.therapist, client=self.patient, starts_at=self.start, ends_at=self.start+timedelta(minutes=50))
        event = CalendarEvent(practice=self.practice, therapist=self.therapist, title='Meeting', starts_at=self.start, ends_at=self.start+timedelta(hours=1))
        layout = AppointmentListView().get_day_timed_entries([appointment], [event])
        first, second = layout['appointments'][0]['style'], layout['events'][0]['style']
        self.assertIn(' / 2', first)
        self.assertIn(' / 2', second)
        self.assertNotEqual(first.split('left:')[1], second.split('left:')[1])

    def test_read_only_user_cannot_write_events(self):
        profile = self.user.nuvia_profile
        profile.role = UserProfile.Role.THERAPIST
        profile.permissions = {'appointments': {'view': True}}
        profile.save()
        response = self.client.post(reverse('appointments:event_create'), self.data)
        self.assertEqual(response.status_code, 302)
        self.assertFalse(CalendarEvent.objects.exists())
