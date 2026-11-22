from datetime import timedelta
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.appointments.models import Appointment
from apps.clients.models import Client
from apps.clinical.models import SessionNote
from apps.portal.models import (
    ClientIntakeAssignment, ClientPortalRequest, IntakePacketTemplate,
    PortalProfileSubmission, PublicBookingRequest,
)
from apps.practices.models import Practice, TherapistProfile


@override_settings(MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False)
class PendingInboxTests(TestCase):
    def setUp(self):
        self.practice = Practice.objects.create(name='Inbox clinic')
        self.user = get_user_model().objects.create_user('inbox-owner')
        self.profile = UserProfile.objects.create(user=self.user, practice=self.practice, role='owner')
        self.therapist = TherapistProfile.objects.create(user=self.user, practice=self.practice,
            license_number='INBOX-1', license_state='CA')
        self.person = Client.objects.create(practice=self.practice, first_name='Demo', last_name='Client')
        self.template = IntakePacketTemplate.objects.create(practice=self.practice, name='Intake', questions=['Goals?'])
        self.form = ClientIntakeAssignment.objects.create(practice=self.practice, client=self.person,
            template=self.template, status='submitted', submitted_at=timezone.now(), answers={'secret': 'PRIVATE ANSWER'})
        self.info = PortalProfileSubmission.objects.create(practice=self.practice, client=self.person,
            submitted_by=self.user, details='{"phone":"PRIVATE PHONE"}')
        self.request = ClientPortalRequest.objects.create(practice=self.practice, client=self.person,
            category='reschedule', subject='PRIVATE SUBJECT', message='PRIVATE MESSAGE')
        self.booking = PublicBookingRequest.objects.create(practice=self.practice,
            first_name='New', last_name='Visitor', email='visitor@example.test',
            requested_starts_at=timezone.now(), requested_ends_at=timezone.now()+timedelta(hours=1))
        self.appointment = Appointment.objects.create(practice=self.practice, client=self.person,
            therapist=self.therapist, starts_at=timezone.now()-timedelta(days=1),
            ends_at=timezone.now()-timedelta(hours=23), status='completed')
        self.note = SessionNote.objects.create(practice=self.practice, client=self.person,
            therapist=self.therapist, content='PRIVATE NOTE')
        self.client.force_login(self.user)

    def inbox(self, **params):
        return self.client.get(reverse('pending_inbox'), params)

    def test_combines_sources_counts_and_links_without_loading_sensitive_bodies(self):
        response = self.inbox()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['pending_total'], 6)
        self.assertEqual({row['item_kind'] for row in response.context['pending_items']},
                         {'form', 'information', 'portal', 'booking', 'note', 'missing_note'})
        for secret in ['PRIVATE ANSWER', 'PRIVATE PHONE', 'PRIVATE SUBJECT', 'PRIVATE MESSAGE', 'PRIVATE NOTE']:
            self.assertNotContains(response, secret)
        self.assertContains(response, reverse('intake:responses', args=[self.form.pk]))
        self.assertContains(response, reverse('clients:profile_submission', args=[self.person.pk, self.info.pk]))
        self.assertContains(response, reverse('clinical:create')+f'?appointment={self.appointment.pk}')
        self.assertIn('no-store', response['Cache-Control'])
        self.assertEqual(response.context['workspace_pending_count'], 6)
        self.assertContains(response, 'data-activity-menu', count=1)

    def test_filters_preserve_total_and_order_oldest_first(self):
        response = self.inbox(type='notes')
        self.assertEqual(response.context['pending_total'], 6)
        self.assertEqual(response.context['page_obj'].paginator.count, 2)
        self.assertEqual([row['item_kind'] for row in response.context['pending_items']], ['missing_note', 'note'])
        self.assertEqual(self.inbox(type='untrusted').context['category'], '')

    def test_completed_work_disappears_and_note_creation_removes_missing_note(self):
        self.form.status = 'reviewed'; self.form.save()
        self.info.status = 'applied'; self.info.save()
        self.request.status = 'resolved'; self.request.save()
        self.booking.status = 'declined'; self.booking.save()
        self.note.appointment = self.appointment; self.note.save()
        response = self.inbox()
        self.assertEqual(response.context['pending_total'], 1)
        self.assertEqual(response.context['pending_items'][0]['item_kind'], 'note')
        self.note.is_locked = True; self.note.save()
        self.assertEqual(self.inbox().context['pending_total'], 0)

    def test_only_completed_past_sessions_without_any_note_are_flagged(self):
        self.appointment.status = 'scheduled'; self.appointment.save()
        self.assertEqual(self.inbox(type='notes').context['page_obj'].paginator.count, 1)
        self.appointment.status = 'completed'
        self.appointment.ends_at = timezone.now()+timedelta(hours=1); self.appointment.save()
        self.assertEqual(self.inbox(type='notes').context['page_obj'].paginator.count, 1)

    def test_foreign_practice_items_and_target_ids_are_not_exposed(self):
        other = Practice.objects.create(name='Other clinic')
        foreign = Client.objects.create(practice=other, first_name='FOREIGN', last_name='PATIENT')
        foreign_request = ClientPortalRequest.objects.create(practice=other, client=foreign,
            category='general', subject='OTHER SECRET', message='OTHER SECRET')
        self.assertNotContains(self.inbox(), 'FOREIGN')
        response = self.client.get(reverse('portal_requests:list'), {'source':'portal', 'item':foreign_request.pk})
        self.assertEqual(response.context['paginator'].count, 0)
        response = self.client.get(reverse('portal_requests:list'), {'source':'portal', 'item':self.request.pk})
        self.assertEqual(response.context['paginator'].count, 1)
        self.assertContains(response, 'PRIVATE SUBJECT')
        foreign_booking = PublicBookingRequest.objects.create(practice=other,
            first_name='Foreign', last_name='Visitor', email='foreign@example.test',
            requested_starts_at=timezone.now(), requested_ends_at=timezone.now()+timedelta(hours=1))
        response = self.client.get(reverse('portal_requests:list'), {'source':'public', 'item':foreign_booking.pk})
        self.assertEqual(response.context['paginator'].count, 0)
        response = self.client.get(reverse('portal_requests:list'), {'source':'public', 'item':self.booking.pk})
        self.assertEqual(response.context['paginator'].count, 1)
        self.assertContains(response, 'New Visitor')

    def test_malformed_request_item_filters_do_not_raise_errors(self):
        for item in ['²', 'x', '9' * 100, '-1']:
            with self.subTest(item=item):
                response = self.client.get(reverse('portal_requests:list'), {'source':'portal', 'item':item})
                self.assertEqual(response.status_code, 200)

    def test_permissions_control_sources_not_tasks_permission(self):
        self.profile.role = 'therapist'
        self.profile.permissions = {'requests': {'view': True}}
        self.profile.save()
        response = self.inbox()
        self.assertEqual(response.context['pending_total'], 2)
        self.assertEqual({row['item_kind'] for row in response.context['pending_items']}, {'portal','booking'})
        self.assertTrue(all(not row['client_url'] for row in response.context['pending_items']))
        self.profile.permissions = {'intake': {'view': True}}; self.profile.save()
        self.assertEqual(self.inbox().context['pending_total'], 0)

    def test_therapists_only_see_their_own_session_documentation(self):
        other = get_user_model().objects.create_user('other-inbox-therapist')
        therapist = TherapistProfile.objects.create(user=other, practice=self.practice,
            license_number='INBOX-2', license_state='CA')
        SessionNote.objects.create(practice=self.practice, client=self.person, therapist=therapist)
        self.profile.role = 'therapist'
        self.profile.permissions = {'clinical': {'view':True}, 'appointments': {'view':True}}
        self.profile.save()
        response = self.inbox(type='notes')
        self.assertEqual(response.context['pending_total'], 1)
        self.assertEqual(response.context['pending_items'][0]['item_id'], self.note.pk)
        self.assertNotContains(response, reverse('clinical:edit', args=[self.note.pk]))

    def test_pagination_counts_every_item_and_has_stable_order(self):
        for _ in range(28):
            ClientIntakeAssignment.objects.create(practice=self.practice, client=self.person,
                template=self.template, status='submitted')
        first = self.inbox(type='forms')
        second = self.inbox(type='forms', page=2)
        self.assertEqual(first.context['page_obj'].paginator.count, 29)
        self.assertEqual(len(first.context['pending_items']), 25)
        self.assertEqual(len(second.context['pending_items']), 4)
        ids = [row['item_id'] for response in [first, second] for row in response.context['pending_items']]
        self.assertEqual(len(set(ids)), 29)
        self.assertContains(first, '?type=forms&amp;page=2')
        self.assertEqual(self.inbox(page='invalid').status_code, 200)

    def test_authentication_and_patient_isolation(self):
        self.client.logout()
        self.assertEqual(self.inbox().status_code, 302)
        self.profile.role = 'client'; self.profile.save()
        self.client.force_login(self.user)
        self.assertRedirects(self.inbox(), reverse('portal:dashboard'), fetch_redirect_response=False)

    def test_no_practice_yields_empty_queue(self):
        user = get_user_model().objects.create_user('unassigned-inbox-admin', is_superuser=True)
        self.client.force_login(user)
        response = self.inbox()
        self.assertEqual(response.context['pending_total'], 0)
        self.assertNotContains(response, 'Demo Client')
