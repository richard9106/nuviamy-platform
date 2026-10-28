from unittest.mock import patch

import boto3
from botocore.stub import Stubber, ANY
from django.core.mail import EmailMessage
from django.test import SimpleTestCase, override_settings

from .ses_backend import EmailBackend


@override_settings(AWS_SES_REGION='us-east-1', AWS_SES_CONFIGURATION_SET='transactional-test',
                   DEFAULT_FROM_EMAIL='NuviaMy <noreply@example.com>')
class SESBackendTests(SimpleTestCase):
    def ses_client(self):
        return boto3.client('sesv2', region_name='us-east-1',
            aws_access_key_id='test-only', aws_secret_access_key='test-only')

    def test_raw_mime_and_configuration_set_are_sent_without_bcc_header(self):
        client = self.ses_client()
        email = EmailMessage('Account invitation', 'Fictional invitation',
            to=['recipient@example.com'], bcc=['hidden@example.com'])
        raw = email.message().as_bytes(linesep='\r\n')
        self.assertNotIn(b'Bcc:', raw)
        with Stubber(client) as stub, patch('apps.accounts.ses_backend.boto3.client', return_value=client):
            stub.add_response('send_email', {'MessageId': 'test-id'}, {
                'FromEmailAddress': email.from_email,
                'Destination': {'ToAddresses': email.recipients()},
                'Content': {'Raw': {'Data': ANY}}, 'ConfigurationSetName': 'transactional-test'})
            self.assertEqual(EmailBackend().send_messages([email]), 1)
            stub.assert_no_pending_responses()

    def test_provider_errors_are_redacted_without_smtp_fallback(self):
        client = self.ses_client()
        email = EmailMessage('Private subject marker', 'Private body marker', to=['private-marker@example.com'])
        with Stubber(client) as stub, patch('apps.accounts.ses_backend.boto3.client', return_value=client):
            stub.add_client_error('send_email', service_error_code='MessageRejected',
                                  service_message='private-marker@example.com Private body marker')
            with self.assertRaises(RuntimeError) as caught:
                EmailBackend().send_messages([email])
            self.assertNotIn('private-marker', str(caught.exception))
            self.assertNotIn('Private body', str(caught.exception))

    def test_different_sender_and_attachments_are_not_sent(self):
        for email in (EmailMessage('Test', 'Test', from_email='other@example.com', to=['a@example.com']),
                      EmailMessage('Test', 'Test', to=['a@example.com'], attachments=[('file.txt', 'data', 'text/plain')])):
            with patch('apps.accounts.ses_backend.boto3.client') as factory:
                with self.assertRaises(RuntimeError):
                    EmailBackend().send_messages([email])
                factory.return_value.send_email.assert_not_called()

    @override_settings(AWS_SES_CONFIGURATION_SET='')
    def test_missing_configuration_set_fails_before_any_provider_call(self):
        from django.core.exceptions import ImproperlyConfigured
        with patch('apps.accounts.ses_backend.boto3.client') as factory:
            with self.assertRaises(ImproperlyConfigured):
                EmailBackend().send_messages([EmailMessage('Test','Test',to=['a@example.com'])])
            factory.assert_not_called()
