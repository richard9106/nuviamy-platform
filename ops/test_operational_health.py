import unittest
from ops.operational_health import notification_due


class AlertDeduplicationTests(unittest.TestCase):
    def test_healthy_checks_never_send_and_repeated_failures_are_limited(self):
        self.assertFalse(notification_due({}, [], 100000))
        self.assertTrue(notification_due({}, ['backup'], 100000))
        previous = {'failure_codes': ['backup'], 'notified_at': 100000}
        self.assertFalse(notification_due(previous, ['backup'], 100001))
        self.assertTrue(notification_due(previous, ['backup'], 186400))
        self.assertTrue(notification_due(previous, ['https_health'], 100001))
