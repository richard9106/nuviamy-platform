from datetime import timedelta
from decimal import Decimal

from django.db import connection
from django.test import RequestFactory, TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.billing.models import Invoice
from apps.clinical.models import SessionNote
from .models import Appointment
from .navigation import session_origin
from .session_summary import prepare_session_summaries


@override_settings(MFA_REQUIRED=False)
class SessionEditorContextTests(TestCase):
    def setUp(self):
        from .tests import AppointmentViewTests
        self.user, self.practice, self.therapist, self.patient = AppointmentViewTests.create_practice_user(self)
        self.other_user, self.other_practice, self.other_therapist, self.other_patient = AppointmentViewTests.create_practice_user(self, username='foreign-editor')
        self.start = timezone.localtime().replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=1)
        self.session = Appointment.objects.create(practice=self.practice, client=self.patient, therapist=self.therapist, starts_at=self.start, ends_at=self.start+timedelta(minutes=50))
        self.return_url = reverse('clients:detail', args=[self.patient.pk]) + '?tab=overview'
        self.client.force_login(self.user)

    def test_client_profile_reuses_editor_and_saves_back_to_profile(self):
        page = self.client.get(self.return_url)
        self.assertContains(page, f'id="appointment-modal-{self.session.pk}"')
        self.assertContains(page, f'data-modal-target="appointment-modal-{self.session.pk}"')
        self.assertContains(page, 'data-editor-panel="records"')
        self.assertContains(page, 'id="appointment-create-modal"')
        self.assertNotContains(page, 'data-editor-tab="out-of-office"')
        self.assertContains(page, f'value="{self.patient.pk}" selected')
        response = self.client.post(reverse('appointments:reschedule', args=[self.session.pk]), {'date': self.start.date().isoformat(), 'time': '11:00', 'next': self.return_url})
        self.assertEqual(response.url, self.return_url)
        self.session.refresh_from_db()
        self.assertEqual(timezone.localtime(self.session.starts_at).hour, 11)
        response = self.client.post(reverse('appointments:create'), {'client': self.patient.pk, 'therapist': self.therapist.pk, 'starts_at': self.start.strftime('%Y-%m-%dT13:00'), 'ends_at': self.start.strftime('%Y-%m-%dT13:50'), 'session_kind': 'standard', 'appointment_type': 'video', 'status': 'scheduled', 'next': self.return_url})
        self.assertEqual(response.url, self.return_url)

    def test_summary_counts_statuses_without_fetching_note_bodies(self):
        fields = {'practice': self.practice, 'client': self.patient, 'therapist': self.therapist, 'appointment': self.session, 'content': 'Confidential body should never be read for a summary'}
        SessionNote.objects.create(**fields)
        signed = SessionNote.objects.create(**fields)
        signed.sign(self.user, signed.review_digest())
        SessionNote.objects.create(**fields, note_type='treatment_plan')
        for index, status in enumerate(('draft', 'sent', 'paid', 'void')):
            Invoice.objects.create(practice=self.practice, client=self.patient, appointment=self.session, invoice_number=f'SUM-{index}', amount=Decimal('100'), status=status, paid_at=timezone.now() if status == 'paid' else None)
        with CaptureQueriesContext(connection) as queries:
            prepare_session_summaries([self.session], self.user)
        self.assertEqual(self.session.note_summary, {'signed': 1, 'unsigned': 1})
        self.assertEqual(dict(self.session.invoice_summary), {'draft': 1, 'sent': 1, 'paid': 1, 'void': 1})
        self.assertNotIn('"content"', ' '.join(q['sql'] for q in queries.captured_queries))
        page = self.client.get(self.return_url)
        self.assertContains(page, '1 signed')
        self.assertContains(page, '1 unsigned')
        self.assertContains(page, '1 paid')
        self.assertNotContains(page, fields['content'])

    def test_denied_sections_and_foreign_sessions_are_not_enriched(self):
        foreign = Appointment.objects.create(practice=self.other_practice, client=self.other_patient, therapist=self.other_therapist, starts_at=self.start, ends_at=self.start+timedelta(minutes=50))
        prepare_session_summaries([foreign], self.user)
        self.assertFalse(hasattr(foreign, 'note_summary'))
        profile = self.user.nuvia_profile
        profile.role = UserProfile.Role.THERAPIST
        profile.permissions = {'clients': {'view': True}, 'appointments': {'view': True, 'edit': True}, 'clinical': {'view': False}, 'billing': {'view': False}}
        profile.save()
        with self.assertNumQueries(0):
            prepare_session_summaries([self.session], self.user)
        self.assertFalse(hasattr(self.session, 'note_summary'))
        page = self.client.get(self.return_url)
        self.assertNotContains(page, 'aria-label="Session record status"')
        self.assertNotContains(page, 'Create invoice')
        self.assertNotContains(page, 'Create note')

    def test_return_origin_rejects_foreign_and_external_urls_for_notes_too(self):
        from apps.clinical.views import session_origin_url
        factory = RequestFactory()
        for target, expected in [
            (self.return_url, self.return_url),
            (reverse('clients:detail', args=[self.other_patient.pk]), None),
            ('https://example.com/', None), ('//example.com/', None),
            ('/clients/', None), ('/clients/999999/', None),
            ('/appointments/?view=week', '/appointments/?view=week'),
        ]:
            with self.subTest(target=target):
                request = factory.get('/', {'next': target})
                request.user = self.user
                self.assertEqual(session_origin(request), expected)
                self.assertEqual(session_origin_url(request), expected)

    def test_note_popup_preserves_client_origin_without_signing_automatically(self):
        from urllib.parse import parse_qs, urlsplit
        url = reverse('clinical:create') + f'?appointment={self.session.pk}&session_list=1'
        response = self.client.post(url, {'client': self.patient.pk, 'therapist': self.therapist.pk,
            'appointment': self.session.pk, 'note_type': 'progress_note', 'content': 'Fictional draft.',
            'next': self.return_url}, HTTP_X_REQUESTED_WITH='XMLHttpRequest')
        self.assertEqual(response.status_code, 200)
        destination = response.json()['redirect']
        note = SessionNote.objects.get()
        self.assertEqual(urlsplit(destination).path, reverse('clinical:sign', args=[note.pk]))
        self.assertEqual(parse_qs(urlsplit(destination).query)['next'], [self.return_url])
        self.assertIsNone(note.signed_at)
        self.assertFalse(note.is_locked)

    def test_summary_queries_are_batched_across_sessions(self):
        sessions = [self.session]
        for index in range(3):
            start = self.start + timedelta(days=index+1)
            sessions.append(Appointment.objects.create(practice=self.practice, client=self.patient, therapist=self.therapist, starts_at=start, ends_at=start+timedelta(minutes=50)))
        _ = self.user.nuvia_profile
        with self.assertNumQueries(3):
            prepare_session_summaries(sessions, self.user)
