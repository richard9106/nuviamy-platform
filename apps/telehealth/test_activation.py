from unittest.mock import patch
from django.test import TestCase,override_settings
from django.urls import reverse
from django.core.management import call_command
from apps.accounts.contract_models import StandardAgreementAcceptance
from apps.accounts.standard_agreements import digest
from apps.practices.models import ExternalIntegration,Practice
from .test_video import EmbeddedVideoTests
from .activation import offer,VERSION,accepted
from .access import enabled_for
from .models import TelehealthRoom


@override_settings(MFA_REQUIRED=False,MFA_PRIVILEGED_REQUIRED=False,EMAIL_TWO_STEP_REQUIRED=False,
 TELEHEALTH_ENABLED=True,TELEHEALTH_GENERAL_AVAILABLE=True,
 STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
class VideoActivationTests(TestCase):
    make_host=EmbeddedVideoTests.make_host
    make_appointment=EmbeddedVideoTests.make_appointment
    post=EmbeddedVideoTests.post

    def setUp(self):
        EmbeddedVideoTests.setUp(self)
        setting=override_settings(TELEHEALTH_PRACTICE_IDS=())
        setting.enable();self.addCleanup(setting.disable)
        profile=self.host.nuvia_profile;profile.role='owner';profile.save()
        self.url=reverse('telehealth:settings')

    def activation(self,**changes):
        data={'action':'enable','representative_name':'Synthetic Owner','accept_scope':'on','scope_confirmed':'on','offer_digest':digest(offer())}
        data.update(changes)
        return self.host_browser.post(self.url,data)

    def test_availability_does_not_enable_calls_until_owner_accepts(self):
        self.assertFalse(enabled_for(self.practice.pk))
        response=self.host_browser.get(self.url)
        self.assertContains(response,'Accept addendum and enable video')
        self.assertContains(response,'EEA clinical-data')
        self.api.create.assert_not_called()
        self.assertEqual(self.activation().status_code,302)
        self.assertTrue(enabled_for(self.practice.pk))
        self.assertFalse(enabled_for(Practice.objects.create(name='Other fictional practice').pk))
        receipt=accepted(self.practice.pk)
        self.assertEqual(receipt.digest,digest(receipt.snapshot))
        self.assertEqual(receipt.signer_id,self.host.pk)
        self.assertEqual(receipt.snapshot['agreement_type'],'telehealth_addendum')
        self.assertIn('telehealth',receipt.snapshot['documents'])
        self.assertIsNotNone(receipt.snapshot['base_acceptance_id'])
        self.api.create.assert_not_called()

    def test_only_owner_can_read_or_activate(self):
        self.assertEqual(self.patient_browser.get(self.url).status_code,403)
        profile=self.host.nuvia_profile;profile.role='therapist';profile.save()
        self.assertEqual(self.activation().status_code,403)
        self.assertFalse(enabled_for(self.practice.pk))

    def test_scope_checkbox_and_current_digest_are_required(self):
        for changes in ({'scope_confirmed':''},{'accept_scope':''},{'offer_digest':'stale'}):
            self.assertEqual(self.activation(**changes).status_code,200)
            self.assertFalse(enabled_for(self.practice.pk))
        self.assertIsNone(accepted(self.practice.pk))

    def test_base_agreement_must_be_ready(self):
        with patch('apps.telehealth.activation.base_ready',return_value=False):
            self.assertEqual(self.activation().status_code,200)
        self.assertIsNone(accepted(self.practice.pk))

    def test_global_switch_blocks_settings_and_activation(self):
        with override_settings(TELEHEALTH_ENABLED=False):
            self.assertEqual(self.host_browser.get(self.url).status_code,404)
            self.assertEqual(self.activation().status_code,404)

    def test_repeated_activation_retains_one_immutable_receipt(self):
        self.activation();original=accepted(self.practice.pk).digest
        self.activation()
        self.assertEqual(StandardAgreementAcceptance.objects.filter(version=VERSION).count(),1)
        self.assertEqual(accepted(self.practice.pk).digest,original)

    def test_disable_preserves_receipt_and_worker_closes_active_room(self):
        self.activation()
        self.assertEqual(self.post().json()['state'],'joined')
        self.assertEqual(self.host_browser.post(self.url,{'action':'disable'}).status_code,302)
        self.assertFalse(enabled_for(self.practice.pk))
        self.assertIsNotNone(accepted(self.practice.pk))
        call_command('cleanup_video_rooms',verbosity=0)
        self.assertEqual(TelehealthRoom.objects.get().status,'ended')
        self.api.terminate.assert_called_once()

    def test_owner_can_disable_operator_pilot_too(self):
        with override_settings(TELEHEALTH_PRACTICE_IDS=(self.practice.pk,)):
            self.assertTrue(enabled_for(self.practice.pk))
            self.host_browser.post(self.url,{'action':'disable'})
            self.assertFalse(enabled_for(self.practice.pk))
