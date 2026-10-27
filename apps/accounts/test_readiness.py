import io
import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command, CommandError
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from apps.accounts.readiness import security_readiness_report


@override_settings(DJANGO_ENVIRONMENT='production', DEBUG=False,
    SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True, SECURE_HSTS_SECONDS=31536000,
    MFA_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=True,
    GOOGLE_REVIEW_USER_ID='', GOOGLE_REVIEW_PRACTICE_ID='', GOOGLE_REVIEW_ACCESS_EXPIRES_AT='',
    EMAIL_BACKEND='django.core.mail.backends.smtp.EmailBackend', EMAIL_USE_TLS=True, EMAIL_USE_SSL=False,
    DJANGO_STORAGE_BACKEND='s3', AWS_S3_ENDPOINT_URL=None, AWS_S3_REGION_NAME='us-east-1',
    SENTRY_TRACES_SAMPLE_RATE=0)
class SecurityReadinessTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(username='private-operator-marker',
            email='private-email-marker@example.com', password='private-password-marker',
            is_superuser=True, is_staff=True)

    def statuses(self, report):
        return {check['code']: check['status'] for check in report['checks']}

    def test_report_is_read_only_and_does_not_disclose_account_or_secret_values(self):
        with override_settings(SECRET_KEY='private-secret-marker', SENTRY_DSN='private-dsn-marker'):
            with CaptureQueriesContext(connection) as queries:
                report = security_readiness_report()
        self.assertTrue(queries)
        self.assertTrue(all(query['sql'].lstrip().upper().startswith('SELECT') for query in queries))
        serialized = json.dumps(report)
        for marker in ('private-operator-marker', 'private-email-marker', 'private-password-marker',
                       'private-secret-marker', 'private-dsn-marker', self.user.password):
            self.assertNotIn(marker, serialized)
        self.assertEqual(report['account_counts']['active_superusers'], 1)
        self.assertFalse(report['compliance_approved'])
        self.assertEqual(self.statuses(report)['privileged_totp'], 'review')

    def test_disabling_both_second_steps_fails(self):
        with override_settings(MFA_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False):
            self.assertEqual(self.statuses(security_readiness_report())['second_step'], 'fail')

    def test_plaintext_mail_custom_storage_and_diagnostic_tracing_fail(self):
        with override_settings(EMAIL_USE_TLS=False, EMAIL_USE_SSL=False,
                               AWS_S3_ENDPOINT_URL='https://private-endpoint.example',
                               SENTRY_TRACES_SAMPLE_RATE=1):
            statuses = self.statuses(security_readiness_report())
        for name in ('mail_transport', 'native_s3', 'diagnostic_tracing'):
            self.assertEqual(statuses[name], 'fail')

    def test_privileged_database_role_fails_and_restricted_role_passes(self):
        for privileges, expected in [((False, False, False, False), 'pass'),
                                     ((True, False, False, False), 'fail'),
                                     ((False, False, False, True), 'fail'), (None, 'fail')]:
            with self.subTest(privileges=privileges), patch('apps.accounts.readiness.connection') as db:
                db.vendor = 'postgresql'
                db.cursor.return_value.__enter__.return_value.fetchone.return_value = privileges
                self.assertEqual(self.statuses(security_readiness_report())['database_role'], expected)

    def test_command_reports_json_before_failing_and_cannot_certify_manual_controls(self):
        output = io.StringIO()
        with self.assertRaises(CommandError):
            call_command('security_readiness', fail_on_review=True, stdout=output)
        report = json.loads(output.getvalue())
        self.assertFalse(report['compliance_approved'])
        self.assertGreater(report['summary']['review'], 0)
