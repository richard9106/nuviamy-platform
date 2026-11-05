"""Synthetic identities only. No real media, camera, AWS calls or credentials."""
from datetime import timedelta
import json
import uuid
from unittest.mock import patch, Mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client as HttpClient, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from apps.accounts.models import UserProfile
from apps.accounts.contract_models import StandardAgreementAcceptance
from apps.accounts.standard_agreements import AGREEMENT_VERSION, digest
from apps.appointments.models import Appointment
from apps.audit.models import AuditLog
from apps.clients.models import Client
from apps.portal.models import ClientPortalAccess
from apps.practices.models import Practice, TherapistProfile
from .models import TelehealthRoom, VideoParticipant, VideoRuntime


@override_settings(MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False,
                   TELEHEALTH_ENABLED=True, TELEHEALTH_PRACTICE_IDS=(1,),
                   STORAGES={'default': {'BACKEND':'django.core.files.storage.FileSystemStorage'},
                             'staticfiles': {'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class EmbeddedVideoTests(TestCase):
    def setUp(self):
        self.practice = Practice.objects.create(name='Synthetic practice')
        self.feature = override_settings(TELEHEALTH_PRACTICE_IDS=(self.practice.pk,))
        self.feature.enable(); self.addCleanup(self.feature.disable)
        self.host = self.make_host('synthetic-host')
        self.patient = get_user_model().objects.create_user('synthetic-patient')
        self.record = Client.objects.create(practice=self.practice, first_name='Fictional',last_name='Patient')
        self.portal = ClientPortalAccess.objects.create(user=self.patient, practice=self.practice, client=self.record)
        UserProfile.objects.create(user=self.patient, practice=self.practice, role='client')
        self.appointment = self.make_appointment(self.host)
        snapshot = {'synthetic': True}
        StandardAgreementAcceptance.objects.create(practice=self.practice, signer=self.host, version=AGREEMENT_VERSION,
                                                  snapshot=snapshot, digest=digest(snapshot))
        VideoRuntime.objects.update_or_create(pk=1, defaults={'last_cleanup_at': timezone.now()})
        self.host_browser = HttpClient(); self.host_browser.force_login(self.host)
        self.patient_browser = HttpClient(); self.patient_browser.force_login(self.patient)
        self.host_nonce = str(uuid.uuid4()); self.patient_nonce = str(uuid.uuid4())
        self.api = Mock()
        for method in ['create', 'issue', 'revoke_role', 'terminate', 'absent']:
            patched = patch('apps.telehealth.provider.'+method, getattr(self.api, method))
            patched.start(); self.addCleanup(patched.stop)
        self.api.create.return_value = {'MeetingId': 'synthetic-meeting', 'MediaRegion': 'us-east-1',
                                       'MediaPlacement': {'AudioHostUrl':'synthetic.invalid'}}
        self.api.issue.side_effect = lambda room,role: {'AttendeeId': role+'-opaque', 'JoinToken': role+'-SECRET-FIXTURE'}
        self.api.absent.return_value = False

    def make_host(self, username):
        user=get_user_model().objects.create_user(username)
        UserProfile.objects.create(user=user, practice=self.practice, role='therapist')
        TherapistProfile.objects.create(user=user, practice=self.practice, license_number=username, license_state='CA')
        return user

    def make_appointment(self, host):
        now=timezone.now()
        return Appointment.objects.create(practice=self.practice, client=self.record,
            therapist=host.therapist_profile, starts_at=now-timedelta(minutes=5), ends_at=now+timedelta(minutes=45), appointment_type='video')

    def post(self, who='host', action='join', nonce=None, pk=None):
        browser=self.host_browser if who=='host' else self.patient_browser
        return browser.post(reverse('telehealth:action', args=[pk or self.appointment.pk]),
            data=json.dumps({'action':action,'nonce':nonce or (self.host_nonce if who=='host' else self.patient_nonce)}),
            content_type='application/json')

    def open_and_admit(self):
        self.post('patient')
        self.assertEqual(self.post().json()['state'],'joined')
        self.assertEqual(self.post(action='admit').status_code,200)

    def test_waiting_patient_never_gets_credentials_or_creates_aws_room(self):
        response=self.post('patient')
        self.assertEqual(response.json()['state'],'waiting')
        self.api.create.assert_not_called();self.api.issue.assert_not_called()
        self.assertNotIn('Attendee',response.json())
        self.assertEqual(self.post('patient',action='heartbeat').json()['state'],'waiting')

    def test_admission_and_credentials_are_for_the_correct_role_only(self):
        self.open_and_admit()
        response=self.post('patient')
        self.assertEqual(response.json()['Attendee']['JoinToken'],'patient-SECRET-FIXTURE')
        self.assertNotIn('host-SECRET-FIXTURE',response.content.decode())
        self.assertEqual(self.api.create.call_count,1)
        self.assertEqual(self.post(action='heartbeat').json()['waiting'],False)

    def test_patient_cannot_admit_or_end_the_room(self):
        self.open_and_admit()
        for action in ['admit','end']:
            self.assertEqual(self.post('patient',action=action).status_code,404)
        self.api.terminate.assert_not_called()

    def test_host_cannot_admit_before_joining(self):
        self.post('patient')
        self.assertEqual(self.post(action='admit').status_code,404)
        self.api.issue.assert_not_called()

    def test_new_patient_browser_requires_new_admission_and_revokes_old_role(self):
        self.open_and_admit();self.post('patient')
        self.assertEqual(self.post('patient',nonce=str(uuid.uuid4())).json()['state'],'waiting')
        self.assertIn('patient',[call.args[1] for call in self.api.revoke_role.call_args_list])
        self.assertEqual(self.post('patient',action='heartbeat').json()['state'],'superseded')

    def test_same_nonce_in_another_login_session_does_not_match(self):
        self.open_and_admit()
        another=HttpClient();another.force_login(self.patient)
        response=another.post(reverse('telehealth:action',args=[self.appointment.pk]),
            data=json.dumps({'action':'heartbeat','nonce':self.patient_nonce}),content_type='application/json')
        self.assertEqual(response.json()['state'],'superseded')

    def test_cross_tenant_and_unassigned_platform_admin_have_no_access(self):
        other_practice=Practice.objects.create(name='Other synthetic practice')
        admin=get_user_model().objects.create_user('synthetic-platform',is_staff=True,is_superuser=True)
        UserProfile.objects.create(user=admin,practice=other_practice,role='owner')
        self.host_browser.force_login(admin)
        self.assertEqual(self.post().status_code,404)
        self.assertEqual(self.host_browser.get(reverse('telehealth:room',args=[self.appointment.pk])).status_code,404)
        UserProfile.objects.filter(user=admin).update(practice=self.practice)
        self.host_browser.force_login(admin)
        self.assertEqual(self.post().status_code,404)
        self.api.create.assert_not_called()

    def test_patient_cannot_access_other_clients_session(self):
        other=Client.objects.create(practice=self.practice,first_name='Other',last_name='Fixture')
        appointment=self.make_appointment(self.host);appointment.client=other;appointment.save()
        self.assertEqual(self.post('patient',pk=appointment.pk).status_code,404)
        self.api.issue.assert_not_called()

    def test_disabled_or_unapproved_feature_does_not_call_provider(self):
        with override_settings(TELEHEALTH_ENABLED=False):
            self.assertEqual(self.post().status_code,404)
        with override_settings(TELEHEALTH_PRACTICE_IDS=()):
            self.assertEqual(self.post().status_code,404)
        self.api.create.assert_not_called()

    def test_contract_gate_is_checked_before_any_credentials(self):
        with patch('apps.telehealth.service.agreements_ready',return_value=False):
            self.assertEqual(self.post().status_code,404)
        self.api.issue.assert_not_called()

    def test_no_permission_or_inactive_portal_cannot_join(self):
        UserProfile.objects.filter(user=self.host).update(permissions={'appointments':{'view':False}})
        self.assertEqual(self.post().status_code,404)
        self.portal.is_active=False;self.portal.save()
        self.assertEqual(self.post('patient').status_code,404)

    def test_stale_worker_fails_closed_before_start(self):
        VideoRuntime.objects.update(last_cleanup_at=timezone.now()-timedelta(minutes=3))
        self.assertEqual(self.post().status_code,503)
        self.api.create.assert_not_called()

    def test_stale_worker_closes_an_existing_session_on_heartbeat(self):
        self.post()
        VideoRuntime.objects.update(last_cleanup_at=timezone.now()-timedelta(minutes=3))
        self.assertEqual(self.post(action='heartbeat').json()['state'],'ended')
        self.api.terminate.assert_called_once()

    def test_outside_join_window_does_not_start_a_meeting(self):
        Appointment.objects.filter(pk=self.appointment.pk).update(starts_at=timezone.now()+timedelta(hours=2),ends_at=timezone.now()+timedelta(hours=3))
        self.assertEqual(self.post().json()['state'],'unavailable')
        self.api.create.assert_not_called()

    def test_manual_links_and_non_video_calls_are_not_replaced(self):
        for values in [{'meeting_url':'https://external.example.invalid'}, {'appointment_type':'phone'}]:
            Appointment.objects.filter(pk=self.appointment.pk).update(**values)
            self.assertEqual(self.post().json()['state'],'unavailable')
        self.api.create.assert_not_called()

    def test_end_clears_room_payload_and_replay_cannot_reopen_same_session(self):
        self.open_and_admit()
        self.assertEqual(self.post(action='end').json()['state'],'ended')
        room=TelehealthRoom.objects.get();self.assertEqual(room.meeting_payload,{})
        self.assertFalse(room.external_room_id)
        self.assertEqual(self.post().json()['state'],'ended')
        self.assertEqual(self.api.create.call_count,1)

    def test_failed_end_persists_closing_fence_for_worker_retry(self):
        self.post();self.api.terminate.side_effect=RuntimeError('sensitive provider failure')
        self.post(action='end')
        self.assertEqual(TelehealthRoom.objects.get().status,'closing')
        self.assertEqual(self.post().json()['state'],'ended')

    def test_provider_failure_is_generic_and_never_exposes_tokens(self):
        self.api.create.side_effect=RuntimeError('provider-secret-fixture')
        response=self.post()
        self.assertEqual(response.status_code,503)
        self.assertNotIn('provider-secret-fixture',response.content.decode())

    def test_lost_attendee_response_retains_meeting_for_cleanup(self):
        self.api.issue.side_effect=RuntimeError('secret-attendee-response')
        response=self.post()
        self.assertEqual(response.status_code,503)
        self.assertNotIn('secret-attendee-response',response.content.decode())
        self.assertEqual(TelehealthRoom.objects.get().external_room_id,'synthetic-meeting')
        TelehealthRoom.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        call_command('cleanup_video_rooms',verbosity=0)
        self.assertEqual(TelehealthRoom.objects.get().status,'ended')

    def test_inactive_subscription_blocks_provider_allocation(self):
        with patch('apps.telehealth.access.subscription_access',return_value={'mode':'read_only'}):
            self.assertEqual(self.post().json()['state'],'unavailable')
        self.api.create.assert_not_called()

    def test_join_tokens_never_persist_in_models_or_audit_metadata(self):
        self.open_and_admit();self.post('patient')
        room=TelehealthRoom.objects.get()
        self.assertNotIn('SECRET',json.dumps(room.meeting_payload))
        self.assertNotIn('SECRET',str(list(VideoParticipant.objects.values())))
        self.assertNotIn('SECRET',str(list(AuditLog.objects.values_list('metadata',flat=True))))
        response=self.post(action='heartbeat')
        self.assertNotIn('Attendee',response.json())
        self.assertIn('no-store',response['Cache-Control'])

    def test_room_headers_and_read_only_get_never_allocate_provider_resources(self):
        response=self.host_browser.get(reverse('telehealth:room',args=[self.appointment.pk]))
        self.assertContains(response,'Test camera &amp; microphone')
        self.assertContains(response,'No recording')
        self.assertIn("frame-ancestors 'none'",response['Content-Security-Policy'])
        self.assertIn('display-capture=()',response['Permissions-Policy'])
        self.assertFalse(TelehealthRoom.objects.exists())
        self.api.create.assert_not_called()
        self.assertEqual(self.host_browser.get(reverse('telehealth:action',args=[self.appointment.pk])).status_code,405)

    def test_csrf_auth_and_invalid_input(self):
        browser=HttpClient(enforce_csrf_checks=True);browser.force_login(self.host)
        url=reverse('telehealth:action',args=[self.appointment.pk])
        self.assertEqual(browser.post(url,data='{}',content_type='application/json').status_code,403)
        self.assertEqual(HttpClient().post(url,data='{}',content_type='application/json').status_code,401)
        self.assertEqual(self.post(nonce='bad').status_code,400)
        self.assertEqual(self.post(action='record').status_code,400)
        self.api.create.assert_not_called()

    def test_capacity_is_bounded_across_appointments(self):
        self.post();second=self.make_host('second-synthetic-host');other=self.make_appointment(second)
        self.host_browser.force_login(second)
        with override_settings(TELEHEALTH_MAX_CONCURRENT_ROOMS=1):
            self.assertEqual(self.post(pk=other.pk,nonce=str(uuid.uuid4())).status_code,503)
        self.assertEqual(self.api.create.call_count,1)

    def test_cancel_and_assignment_change_close_on_commit(self):
        self.post()
        with self.captureOnCommitCallbacks(execute=True):
            self.appointment.status='cancelled';self.appointment.save()
        self.api.terminate.assert_called_once()
        self.assertEqual(self.post().json()['state'],'unavailable')

    def test_bulk_changes_are_caught_by_cleanup_even_without_save_signal(self):
        self.post()
        Appointment.objects.filter(pk=self.appointment.pk).update(status='cancelled')
        call_command('cleanup_video_rooms',verbosity=0)
        self.assertEqual(TelehealthRoom.objects.get().status,'ended')

    def test_expired_room_and_revoked_portal_are_cleaned(self):
        self.open_and_admit();self.post('patient')
        self.portal.is_active=False;self.portal.save()
        call_command('cleanup_video_rooms',verbosity=0)
        self.assertEqual(VideoParticipant.objects.get(role='patient').state,'left')
        TelehealthRoom.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        call_command('cleanup_video_rooms',verbosity=0)
        self.assertEqual(TelehealthRoom.objects.get().status,'ended')

    def test_cleanup_failure_does_not_refresh_safety_heartbeat(self):
        self.post();previous=timezone.now()-timedelta(minutes=4)
        VideoRuntime.objects.update(last_cleanup_at=previous)
        TelehealthRoom.objects.update(expires_at=timezone.now()-timedelta(seconds=1))
        self.api.terminate.side_effect=RuntimeError('fixture')
        with self.assertRaises(CommandError):call_command('cleanup_video_rooms',verbosity=0)
        self.assertEqual(VideoRuntime.objects.get(pk=1).last_cleanup_at,previous)
        self.assertEqual(TelehealthRoom.objects.get().status,'closing')


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, close_old_connections
from apps.audit.testing import ProtectedRecordsTransactionTestCase


@skipUnless(connection.vendor == 'postgresql', 'Real row-lock verification requires PostgreSQL')
@override_settings(MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False,
                   TELEHEALTH_ENABLED=True, TELEHEALTH_MAX_CONCURRENT_ROOMS=1)
class VideoConcurrencyTests(ProtectedRecordsTransactionTestCase):
    setUp = EmbeddedVideoTests.setUp
    make_host = EmbeddedVideoTests.make_host
    make_appointment = EmbeddedVideoTests.make_appointment

    def race(self, appointments):
        barrier = Barrier(2)
        cookies = self.host_browser.cookies
        def join(pk):
            close_old_connections()
            try:
                browser = HttpClient(); browser.cookies = cookies.copy()
                barrier.wait(timeout=10)
                return browser.post(reverse('telehealth:action', args=[pk]),
                    data=json.dumps({'action':'join','nonce':str(uuid.uuid4())}),content_type='application/json').status_code
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as workers:
            return list(workers.map(join, appointments))

    def test_parallel_same_appointment_creates_only_one_meeting(self):
        self.assertEqual(self.race([self.appointment.pk]*2), [200,200])
        self.assertEqual(self.api.create.call_count,1)
        self.assertEqual(TelehealthRoom.objects.exclude(external_room_id='').count(),1)

    def test_parallel_different_appointments_respect_global_capacity(self):
        other = self.make_appointment(self.host)
        self.assertEqual(sorted(self.race([self.appointment.pk,other.pk])),[200,503])
        self.assertEqual(self.api.create.call_count,1)
