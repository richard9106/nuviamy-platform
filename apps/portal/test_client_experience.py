from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.appointments.models import Appointment
from apps.billing.models import Invoice
from apps.clients.models import Client
from apps.practices.models import Practice, TherapistProfile
from .intake_schema import flatten_schema
from .models import ClientIntakeAssignment, ClientPortalAccess, IntakePacketTemplate, PortalConversation, PortalMessage
from .test_intake_builder import schema


@override_settings(MFA_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False)
class ClientExperienceTests(TestCase):
    def setUp(self):
        self.practice = Practice.objects.create(name='Portal practice')
        self.user = get_user_model().objects.create_user('portal-patient')
        self.patient = Client.objects.create(practice=self.practice, first_name='Demo', last_name='Patient')
        UserProfile.objects.create(user=self.user, practice=self.practice, role='client')
        ClientPortalAccess.objects.create(user=self.user, practice=self.practice, client=self.patient)
        staff = get_user_model().objects.create_user('portal-therapist')
        self.therapist = TherapistProfile.objects.create(user=staff, practice=self.practice)
        self.other_patient = Client.objects.create(practice=self.practice, first_name='Other', last_name='Patient')
        self.client.force_login(self.user)

    def appointment(self, **kwargs):
        start = timezone.now() + timedelta(days=2)
        return Appointment.objects.create(
            **{'practice': self.practice, 'client': self.patient, 'therapist': self.therapist,
               'starts_at': start, 'ends_at': start + timedelta(minutes=50), **kwargs})

    def assignment(self, **kwargs):
        template, _ = IntakePacketTemplate.objects.get_or_create(practice=self.practice, name='Welcome form', defaults={'questions': flatten_schema(schema())})
        return ClientIntakeAssignment.objects.create(practice=self.practice, template=template,
            **{'client': self.patient, **kwargs})

    def test_next_session_excludes_cancelled_and_completed_but_keeps_ongoing(self):
        cancelled = self.appointment(status=Appointment.Status.CANCELLED)
        completed = self.appointment(status=Appointment.Status.COMPLETED)
        future = self.appointment()
        ongoing = self.appointment(starts_at=timezone.now()-timedelta(minutes=10), ends_at=timezone.now()+timedelta(minutes=40))
        response = self.client.get(reverse('portal:dashboard'))
        self.assertEqual(response.context['next_appointment'], ongoing)
        self.assertEqual([a.pk for a in response.context['upcoming_appointments']], [ongoing.pk, future.pk])
        self.assertEqual({a.pk for a in response.context['appointment_history']}, {cancelled.pk, completed.pk})
        self.assertNotContains(response, f'data-modal-target="appointment-change-{cancelled.pk}"')

    def test_join_link_only_for_owned_scheduled_video_with_safe_url(self):
        safe = 'https://meet.google.com/abc-defg-hij'
        self.appointment(appointment_type='video', meeting_url=safe)
        self.appointment(appointment_type='video', meeting_url='javascript:alert(1)')
        self.appointment(appointment_type='phone', meeting_url='https://example.com/phone-only')
        self.appointment(client=self.other_patient, appointment_type='video', meeting_url='https://example.com/private')
        response = self.client.get(reverse('portal:dashboard'))
        self.assertContains(response, f'href="{safe}"')
        self.assertNotContains(response, 'javascript:')
        self.assertNotContains(response, 'https://example.com/phone-only')
        self.assertNotContains(response, 'https://example.com/private')
        self.assertContains(response, 'Times shown in')

    def test_opening_selected_conversation_marks_only_its_staff_messages_read(self):
        first = PortalConversation.objects.create(practice=self.practice, client=self.patient, subject='First')
        second = PortalConversation.objects.create(practice=self.practice, client=self.patient, subject='Second')
        first_message = PortalMessage.objects.create(practice=self.practice, conversation=first, author_kind='staff', body='Welcome')
        second_message = PortalMessage.objects.create(practice=self.practice, conversation=second, author_kind='staff', body='Reminder')
        response = self.client.get(reverse('portal:conversations'))
        self.assertContains(response, reverse('portal:conversation_detail', args=[first.public_id]))
        first_message.refresh_from_db(); self.assertIsNone(first_message.read_at)
        response = self.client.get(reverse('portal:conversation_detail', args=[first.public_id]))
        self.assertEqual(response.status_code, 200)
        first_message.refresh_from_db(); second_message.refresh_from_db()
        self.assertIsNotNone(first_message.read_at); self.assertIsNone(second_message.read_at)
        self.assertEqual(self.client.get(reverse('portal:dashboard')).context['unread_message_count'], 1)
        self.assertRedirects(self.client.get(reverse('portal:conversations'), {'open': str(first.public_id)}), reverse('portal:conversation_detail', args=[first.public_id]))
        self.assertEqual(self.client.get(reverse('portal:conversations'), {'open': 'invalid'}).status_code, 200)

    def test_foreign_conversation_is_not_marked_read(self):
        conversation = PortalConversation.objects.create(practice=self.practice, client=self.other_patient, subject='Private')
        message = PortalMessage.objects.create(practice=self.practice, conversation=conversation, author_kind='staff', body='Private')
        self.assertEqual(self.client.get(reverse('portal:conversations'), {'open': str(conversation.public_id)}).status_code, 404)
        message.refresh_from_db(); self.assertIsNone(message.read_at)

    def test_draft_saves_partial_answers_and_can_resume_but_final_requires_completion(self):
        assignment = self.assignment(); url = reverse('portal:intake_complete', args=[assignment.pk])
        response = self.client.post(url, {'action': 'save_draft', 'question_0': 'Maya'}, follow=True)
        self.assertContains(response, 'Draft saved.')
        assignment.refresh_from_db()
        self.assertEqual(assignment.status, 'assigned'); self.assertIsNone(assignment.submitted_at)
        self.assertEqual(assignment.answers['question_0']['answer'], 'Maya')
        self.assertContains(self.client.get(url), 'value="Maya"')
        self.client.post(url, {'question_0': 'Maya'})
        assignment.refresh_from_db(); self.assertEqual(assignment.status, 'assigned')
        response = self.client.post(url, {'question_0': 'Maya', 'question_2': 'Email', 'question_3': ['Work'], 'question_5': 'No'}, follow=True)
        self.assertContains(response, 'Form submitted.')
        assignment.refresh_from_db(); self.assertEqual(assignment.status, 'submitted')
        self.assertContains(response, reverse('portal:intake_responses', args=[assignment.pk]))
        self.assertEqual(self.client.post(url, {'action': 'save_draft', 'question_0': 'Overwrite'}).status_code, 404)
        assignment.refresh_from_db(); self.assertEqual(assignment.answers['question_0']['answer'], 'Maya')

    def test_draft_rejects_invalid_choices_and_length(self):
        assignment = self.assignment(); url = reverse('portal:intake_complete', args=[assignment.pk])
        for payload in [{'question_2': 'Invalid'}, {'question_0': 'x'*501}]:
            response = self.client.post(url, {'action': 'save_draft', **payload})
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
            assignment.refresh_from_db(); self.assertEqual(assignment.answers, {})

    def test_submitted_responses_are_read_only_and_scoped(self):
        assignment = self.assignment(status='submitted', submitted_at=timezone.now(), answers={'question_0': {'question': 'Preferred name', 'answer': '<script>private</script>'}})
        url = reverse('portal:intake_responses', args=[assignment.pk])
        response = self.client.get(url)
        self.assertContains(response, '&lt;script&gt;private&lt;/script&gt;')
        self.assertNotContains(response, '<script>private</script>')
        self.assertEqual(self.client.post(url, {}).status_code, 405)
        foreign = self.assignment(client=self.other_patient, status='submitted')
        self.assertEqual(self.client.get(reverse('portal:intake_responses', args=[foreign.pk])).status_code, 404)
        draft = self.assignment()
        self.assertEqual(self.client.get(reverse('portal:intake_responses', args=[draft.pk])).status_code, 404)

    def test_paid_history_excludes_other_patients_and_drafts(self):
        for patient, number, status in [(self.patient, 'PAID-OWN', 'paid'), (self.other_patient, 'PAID-PRIVATE', 'paid'), (self.patient, 'DRAFT-PRIVATE', 'draft')]:
            Invoice.objects.create(practice=self.practice, client=patient, invoice_number=number, status=status, amount=Decimal('120'), paid_at=timezone.now() if status=='paid' else None)
        response = self.client.get(reverse('portal:dashboard'))
        self.assertContains(response, 'PAID-OWN'); self.assertNotContains(response, 'PAID-PRIVATE'); self.assertNotContains(response, 'DRAFT-PRIVATE')

    def test_invalid_general_request_preserves_dashboard_context(self):
        self.appointment(appointment_type='video', meeting_url='https://meet.google.com/test')
        response = self.client.post(reverse('portal:request_create'), {})
        self.assertEqual(response.status_code, 400)
        self.assertIn('next_appointment', response.context_data)
        self.assertContains(response, 'Join session', status_code=400)
        self.assertContains(response, 'Your to-do list', status_code=400)

    def test_practice_receives_answers_only_after_final_submission(self):
        assignment = self.assignment(answers={'question_0': {'question': 'Preferred name', 'answer': 'Private draft'}})
        owner = get_user_model().objects.create_user('portal-owner')
        UserProfile.objects.create(user=owner, practice=self.practice, role='owner')
        self.client.force_login(owner)
        url = reverse('intake:responses', args=[assignment.pk])
        response = self.client.get(url)
        self.assertNotContains(response, 'Private draft')
        self.assertFalse(response.context['can_review'])
        assignment.status = 'submitted'; assignment.submitted_at = timezone.now(); assignment.save()
        response = self.client.get(url)
        self.assertContains(response, 'Private draft')
        self.assertTrue(response.context['can_review'])
