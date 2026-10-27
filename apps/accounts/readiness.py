"""Read-only, deliberately bounded evidence; this is not a compliance certification."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.utils import timezone

from .models import AccountSecurity


def security_readiness_report():
    checks = []

    def add(code, status, message):
        checks.append({'code': code, 'status': status, 'message': message})

    def require(code, valid, message):
        add(code, 'pass' if valid else 'fail', message)

    require('production', settings.DJANGO_ENVIRONMENT == 'production' and not settings.DEBUG,
            'Production environment with debugging disabled.')
    require('https_sessions', all((settings.SECURE_SSL_REDIRECT, settings.SESSION_COOKIE_SECURE,
            settings.CSRF_COOKIE_SECURE, settings.SESSION_COOKIE_HTTPONLY,
            settings.SECURE_HSTS_SECONDS > 0)), 'HTTPS, secure cookies and HSTS enabled.')
    require('second_step', settings.MFA_REQUIRED or settings.EMAIL_TWO_STEP_REQUIRED,
            'A second authentication step is required globally.')
    require('review_bypass_removed', not any(getattr(settings, key, '') for key in (
            'GOOGLE_REVIEW_USER_ID', 'GOOGLE_REVIEW_PRACTICE_ID', 'GOOGLE_REVIEW_ACCESS_EXPIRES_AT')),
            'Temporary reviewer bypass settings are absent.')
    smtp = settings.EMAIL_BACKEND == 'django.core.mail.backends.smtp.EmailBackend'
    require('mail_transport', smtp and (settings.EMAIL_USE_TLS != settings.EMAIL_USE_SSL),
            'Production account email uses SMTP with exactly one encrypted transport mode.')
    require('native_s3', settings.DJANGO_STORAGE_BACKEND == 's3'
            and not getattr(settings, 'AWS_S3_ENDPOINT_URL', None)
            and getattr(settings, 'AWS_S3_REGION_NAME', '') not in ('', 'auto'),
            'Application documents use native S3 with an explicit region, not a custom endpoint.')
    require('diagnostic_tracing', settings.SENTRY_TRACES_SAMPLE_RATE == 0,
            'External diagnostic performance tracing is disabled.')

    users = get_user_model().objects.filter(is_active=True)
    privileged = users.filter(is_staff=True) | users.filter(is_superuser=True)
    privileged_count = privileged.count()
    enrolled = AccountSecurity.objects.filter(user__in=privileged, confirmed=True).count()
    add('privileged_totp', 'pass' if privileged_count and enrolled == privileged_count else 'review',
        'Review privileged TOTP enrollment and offline recovery; email verification is a separate control.')
    add('privileged_access', 'review', 'Review each active privileged account and document its purpose.')
    counts = {'active_users': users.count(), 'active_privileged_users': privileged_count,
              'active_superusers': users.filter(is_superuser=True).count(),
              'privileged_totp_enrolled': enrolled}
    if connection.vendor == 'postgresql':
        with connection.cursor() as cursor:
            cursor.execute('SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls '
                           'FROM pg_roles WHERE rolname = current_user')
            privileges = cursor.fetchone()
        require('database_role', privileges is not None and not any(privileges),
                'Runtime database role has no superuser, database/role creation or RLS bypass privileges.')
    else:
        add('database_role', 'fail', 'Production runtime must use PostgreSQL with restricted privileges.')

    add('manual_evidence', 'review', 'Check provider contracts, AWS Artifact acceptance, bucket policies, '
        'backup recovery and alerting, device protection, retention, training and incident response separately.')
    return {'schema_version': 1, 'observed_at': timezone.now().isoformat(),
            'scope': 'Runtime configuration and aggregate account metadata only; no remote API calls or writes.',
            'compliance_approved': False, 'checks': checks, 'account_counts': counts,
            'summary': {status: sum(c['status'] == status for c in checks)
                        for status in ('pass', 'fail', 'review')}}
