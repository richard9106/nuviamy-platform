from unittest.mock import patch
from django.test import Client as Browser, TestCase, override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.accounts.models import UserProfile
from apps.clients.models import Client
from apps.clinical.models import SessionNote
from apps.practices.models import Practice, TherapistProfile
from apps.portal.models import ClientPortalRequest
from . import test_inbox


@override_settings(MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False)
class PendingInboxActionTests(TestCase):
    setUp = test_inbox.PendingInboxTests.setUp
    inbox = test_inbox.PendingInboxTests.inbox

    def framed_post(self, name, data=None, args=None):
        return self.client.post(reverse(name, args=args) + '?_workspace_drawer=1', data or {})

    def test_source_reviews_and_read_only_details_only_allow_first_party_framing(self):
        routes = [reverse('intake:responses', args=[self.form.pk]),
                  reverse('clients:profile_submission', args=[self.person.pk, self.info.pk]),
                  reverse('pending_inbox_detail', args=['portal', self.request.pk]),
                  reverse('pending_inbox_detail', args=['booking', self.booking.pk]),
                  reverse('pending_inbox_detail', args=['note', self.note.pk])]
        for path in routes:
            with self.subTest(path=path):
                normal = self.client.get(path)
                framed = self.client.get(path, {'_workspace_drawer':'1'})
                self.assertEqual(normal.status_code, 200)
                self.assertEqual(normal['X-Frame-Options'], 'DENY')
                self.assertEqual(framed['X-Frame-Options'], 'SAMEORIGIN')
                self.assertIn('no-store', framed['Cache-Control'])
                self.assertContains(framed, 'data-workspace-review')
        response = self.client.get(routes[2])
        self.assertContains(response, 'PRIVATE MESSAGE')
        self.assertContains(response, reverse('portal_requests:status', args=[self.request.pk]))

    def test_review_completion_updates_original_record_and_inbox(self):
        response = self.framed_post('intake:review', args=[self.form.pk])
        self.assertContains(response, 'data-workspace-drawer-result="complete"')
        self.form.refresh_from_db()
        self.assertEqual(self.form.status, 'reviewed')
        self.assertEqual(self.inbox().context['pending_total'], 5)
        self.assertEqual(self.framed_post('portal_requests:status', {'status':'resolved'}, [self.request.pk]).status_code, 200)
        self.assertEqual(self.inbox().context['pending_total'], 4)

    def test_profile_validation_retry_is_distinct_from_completed_review(self):
        response = self.framed_post('clients:profile_submission', {'action':'reviewed'}, [self.person.pk, self.info.pk])
        self.assertContains(response, 'data-workspace-drawer-result="retry"')
        self.info.refresh_from_db()
        self.assertEqual(self.info.status, 'pending')
        response = self.framed_post('clients:profile_submission', {'action':'reviewed', 'confirm':'on'}, [self.person.pk, self.info.pk])
        self.assertContains(response, 'data-workspace-drawer-result="complete"')
        self.info.refresh_from_db()
        self.assertEqual(self.info.status, 'reviewed')

    @patch('apps.portal.views.sync_appointment_to_google')
    def test_booking_outcomes_keep_original_validation_and_completion(self, sync):
        empty = Practice.objects.create(name='No therapist clinic')
        self.booking.practice = empty; self.booking.save()
        self.profile.practice = empty; self.profile.save()
        response = self.framed_post('portal_requests:booking_approve', args=[self.booking.pk])
        self.assertContains(response, 'data-workspace-drawer-result="retry"')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'pending')
        sync.assert_not_called()
        response = self.framed_post('portal_requests:booking_decline', args=[self.booking.pk])
        self.assertContains(response, 'data-workspace-drawer-result="complete"')
        self.booking.refresh_from_db()
        self.assertEqual(self.booking.status, 'declined')

    def test_note_edit_validation_stays_in_editor_and_success_returns_to_queue(self):
        path = reverse('clinical:edit', args=[self.note.pk]) + '?_workspace_drawer=1'
        response = self.client.post(path, {'content':'Incomplete'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertNotContains(response, 'data-workspace-drawer-result="complete"')
        response = self.client.post(path, {'client':self.person.pk, 'therapist':self.therapist.pk,
            'content':'Updated fictional draft', 'note_type':'general_note'})
        self.assertContains(response, 'data-workspace-drawer-result="complete"')
        self.note.refresh_from_db()
        self.assertEqual(self.note.content, 'Updated fictional draft')
        self.assertFalse(self.note.is_locked)

    def test_readers_cannot_mutate_and_cannot_read_other_therapists_notes(self):
        self.profile.role = 'therapist'
        self.profile.permissions = {'requests':{'view':True}, 'clinical':{'view':True}}
        self.profile.save()
        detail = reverse('pending_inbox_detail', args=['portal', self.request.pk])
        self.assertNotContains(self.client.get(detail), 'Resolve request')
        response = self.framed_post('portal_requests:status', {'status':'resolved'}, [self.request.pk])
        self.assertNotContains(response, 'data-workspace-drawer-result="complete"')
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, 'new')
        user = get_user_model().objects.create_user('other-note-owner')
        therapist = TherapistProfile.objects.create(user=user, practice=self.practice,
            license_number='ACTION-OTHER', license_state='CA')
        note = SessionNote.objects.create(practice=self.practice, client=self.person, therapist=therapist)
        self.assertEqual(self.client.get(reverse('pending_inbox_detail', args=['note', note.pk])).status_code, 404)
        self.assertContains(self.client.get(reverse('pending_inbox_detail', args=['note', self.note.pk])), 'PRIVATE NOTE')

    def test_new_details_are_tenant_scoped_and_require_permissions(self):
        practice = Practice.objects.create(name='Foreign detail clinic')
        person = Client.objects.create(practice=practice, first_name='Foreign', last_name='Client')
        record = ClientPortalRequest.objects.create(practice=practice, client=person,
            category='general', subject='Foreign secret', message='Foreign secret')
        response = self.client.get(reverse('pending_inbox_detail', args=['portal', record.pk]), {'_workspace_drawer':'1'})
        self.assertEqual(response.status_code, 404)
        self.assertNotContains(response, 'Foreign secret', status_code=404)
        self.profile.role = 'therapist'; self.profile.permissions = {'tasks':{'view':True}}; self.profile.save()
        response = self.client.get(reverse('pending_inbox_detail', args=['portal', self.request.pk]))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['X-Frame-Options'], 'DENY')

    def test_csrf_and_full_page_fallback_are_preserved(self):
        browser = Browser(enforce_csrf_checks=True); browser.force_login(self.user)
        response = browser.post(reverse('intake:review', args=[self.form.pk])+'?_workspace_drawer=1')
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response['X-Frame-Options'], 'DENY')
        self.form.refresh_from_db(); self.assertEqual(self.form.status, 'submitted')
        response = self.client.post(reverse('intake:review', args=[self.form.pk]))
        self.assertRedirects(response, reverse('intake:list'), fetch_redirect_response=False)

    def test_patient_and_anonymous_visitors_do_not_receive_review_content(self):
        path = reverse('pending_inbox_detail', args=['portal', self.request.pk])
        self.client.logout()
        self.assertEqual(self.client.get(path).status_code, 302)
        self.profile.role = 'client'; self.profile.save(); self.client.force_login(self.user)
        response = self.client.get(path)
        self.assertRedirects(response, reverse('portal:dashboard'), fetch_redirect_response=False)
