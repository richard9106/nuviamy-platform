import unittest
from unittest.mock import patch
import boto3
from botocore.stub import Stubber
from ops.operational_health import notification_due, feedback_clear, video_runtime_checks


class AlertDeduplicationTests(unittest.TestCase):
    def test_video_monitor_reports_only_known_flags_and_fails_closed(self):
        with patch('ops.operational_health.checked') as command:
            command.return_value=b'{"enabled":false}'
            self.assertEqual(video_runtime_checks('/synthetic'),{})
            command.return_value=b'{"enabled":true,"cleanup_fresh":false,"revocations_clear":true}'
            self.assertEqual(video_runtime_checks('/synthetic'),{'video_cleanup_fresh':False,'video_revocations_clear':True})
            command.return_value=b'{"enabled":"false"}'
            self.assertEqual(video_runtime_checks('/synthetic'),{'video_runtime_status':False})
            command.side_effect=RuntimeError('raw diagnostic must remain private')
            self.assertEqual(video_runtime_checks('/synthetic'),{'video_runtime_status':False})

    def test_healthy_checks_never_send_and_repeated_failures_are_limited(self):
        self.assertFalse(notification_due({}, [], 100000))
        self.assertTrue(notification_due({}, ['backup'], 100000))
        previous = {'failure_codes': ['backup'], 'notified_at': 100000}
        self.assertFalse(notification_due(previous, ['backup'], 100001))
        self.assertTrue(notification_due(previous, ['backup'], 186400))
        self.assertTrue(notification_due(previous, ['https_health'], 100001))

    def test_feedback_monitor_reads_only_queue_counters_and_detects_backlog(self):
        url = 'https://sqs.us-east-1.amazonaws.com/000000000000/feedback-test'
        client = boto3.client('sqs', region_name='us-east-1',
                              aws_access_key_id='test', aws_secret_access_key='test')
        fields = ['ApproximateNumberOfMessages', 'ApproximateNumberOfMessagesNotVisible',
                  'ApproximateNumberOfMessagesDelayed']
        with Stubber(client) as stub, patch('ops.operational_health.boto3.client', return_value=client):
            for count in ('0', '1'):
                attrs = {field: '0' for field in fields}
                attrs[fields[0]] = count
                stub.add_response('get_queue_attributes', {'Attributes': attrs},
                                  {'QueueUrl': url, 'AttributeNames': fields})
                self.assertEqual(feedback_clear(url), count == '0')
            stub.assert_no_pending_responses()
        with patch('ops.operational_health.boto3.client') as factory:
            with self.assertRaises(ValueError):
                feedback_clear('https://unexpected.example/feedback')
            factory.assert_not_called()
