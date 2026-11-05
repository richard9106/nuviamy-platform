"""Validate real botocore request schemas without network/media/credentials."""
from types import SimpleNamespace
from unittest.mock import patch
import boto3
from botocore.stub import Stubber
from django.test import SimpleTestCase
from . import provider


class ProviderProtocolTests(SimpleTestCase):
    def setUp(self):
        self.client = boto3.client('chime-sdk-meetings', region_name='us-east-1',
            aws_access_key_id='synthetic', aws_secret_access_key='synthetic')
        self.stub = Stubber(self.client)
        self.stub.activate(); self.addCleanup(self.stub.deactivate)
        self.patch = patch.object(provider, 'client', return_value=self.client)
        self.patch.start(); self.addCleanup(self.patch.stop)
        self.room = SimpleNamespace(control_region='us-east-1', external_room_id='meeting-fixture', appointment_fingerprint='a'*64)

    def test_create_caps_two_people_and_disables_content(self):
        self.stub.add_response('create_meeting', {'Meeting': {'MeetingId': 'meeting-fixture'}}, {
            'ClientRequestToken':'a'*64, 'ExternalMeetingId':'nuvia-'+'a'*40, 'MediaRegion':'us-east-1',
            'MeetingFeatures':{'Attendee':{'MaxCount':2}, 'Video':{'MaxResolution':'HD'}, 'Content':{'MaxResolution':'None'}},
            'Tags':[{'Key':'Application','Value':'NuviaMyTelehealth'}]})
        self.assertEqual(provider.create('us-east-1','us-east-1','a'*64)['MeetingId'], 'meeting-fixture')
        self.stub.assert_no_pending_responses()

    def test_rotate_own_role_only_before_issuing_credentials(self):
        host = provider.role_id(self.room,'host'); patient = provider.role_id(self.room,'patient')
        self.stub.add_response('list_attendees', {'Attendees':[
            {'AttendeeId':'old-host','ExternalUserId':host,'JoinToken':'never-log'},
            {'AttendeeId':'patient','ExternalUserId':patient,'JoinToken':'never-log-either'}]}, {'MeetingId':'meeting-fixture'})
        self.stub.add_response('delete_attendee', {}, {'MeetingId':'meeting-fixture','AttendeeId':'old-host'})
        self.stub.add_response('create_attendee', {'Attendee':{'AttendeeId':'new-host','JoinToken':'synthetic-secret'}}, {
            'MeetingId':'meeting-fixture','ExternalUserId':host,
            'Capabilities':{'Audio':'SendReceive','Video':'SendReceive','Content':'None'}})
        self.assertEqual(provider.issue(self.room,'host')['AttendeeId'],'new-host')
        self.stub.assert_no_pending_responses()

    def test_deleting_already_closed_meeting_is_idempotent(self):
        self.stub.add_client_error('delete_meeting', service_error_code='NotFoundException',
            expected_params={'MeetingId':'meeting-fixture'})
        provider.terminate(self.room)
        self.stub.assert_no_pending_responses()
