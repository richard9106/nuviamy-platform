"""Close temporary reviewer access and reconcile legacy Google permissions."""
import json
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.accounts.review_access import REVIEW_USERNAME, REVIEW_PRACTICE_SLUG
from apps.audit.models import AuditLog
from apps.practices.google_policy import CALENDAR_SCOPE, grants_are_approved
from apps.practices.models import ExternalIntegration


class Command(BaseCommand):
    help = 'Preview approval cleanup; use --apply to disable the isolated reviewer and obsolete Google capabilities.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        apply = options['apply']
        reviewer = get_user_model().objects.select_for_update().filter(username=REVIEW_USERNAME).first()
        if reviewer:
            profile = getattr(reviewer, 'nuvia_profile', None)
            therapist = getattr(reviewer, 'therapist_profile', None)
            if (reviewer.is_staff or reviewer.is_superuser or not profile or not therapist
                    or profile.role != 'therapist' or therapist.practice_id != profile.practice_id
                    or profile.practice.public_booking_slug != REVIEW_PRACTICE_SLUG):
                raise CommandError('Reserved reviewer identity does not match the isolated review practice. No changes applied.')
        changed = 0
        reconnect = 0
        for integration in ExternalIntegration.objects.select_for_update().filter(provider='google'):
            changes = {key: False for key in ['send_email_enabled', 'read_email_enabled', 'file_storage_enabled']
                       if getattr(integration, key)}
            expected = [CALENDAR_SCOPE] if integration.calendar_enabled else []
            if integration.enabled_scopes != expected:
                changes['enabled_scopes'] = expected
            if not grants_are_approved(integration.granted_scopes):
                for key, value in [('access_token', ''), ('refresh_token', ''), ('oauth_state', ''),
                                   ('granted_scopes', []), ('token_expires_at', None)]:
                    if getattr(integration, key) != value:
                        changes[key] = value
                if integration.status == ExternalIntegration.Status.CONNECTED:
                    changes['status'] = ExternalIntegration.Status.NEEDS_REAUTH
                    reconnect += 1
            if changes:
                changed += 1
                if apply:
                    for key, value in changes.items():
                        setattr(integration, key, value)
                    integration.save(update_fields=[*changes, 'updated_at'])
                    AuditLog.objects.create(practice=integration.practice, action=AuditLog.Action.UPDATE,
                        object_type='practices.ExternalIntegration', object_id=str(integration.pk),
                        metadata={'google_approval_cleanup': True, 'requires_reauthorization': integration.status == 'needs_reauth'})
        disable_reviewer = bool(reviewer and reviewer.is_active)
        if apply and disable_reviewer:
            reviewer.is_active = False
            reviewer.save(update_fields=['is_active'])
            AuditLog.objects.create(practice=reviewer.nuvia_profile.practice, action=AuditLog.Action.UPDATE,
                object_type='auth.User', object_id=str(reviewer.pk),
                metadata={'google_review_access_closed': True})
        self.stdout.write(json.dumps({'applied': apply, 'integrations_changed': changed,
            'connected_integrations_requiring_reconnect': reconnect, 'reviewer_deactivated': disable_reviewer}))
