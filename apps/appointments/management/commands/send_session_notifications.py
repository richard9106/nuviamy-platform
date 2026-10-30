from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.appointments.models import SessionEmailNotification
from apps.appointments.notifications import deliver_session_email


class Command(BaseCommand):
    help = 'Retry a bounded batch of opted-in therapist email alerts. No SMS sends.'

    def handle(self, *args, **options):
        ids = list(SessionEmailNotification.objects.filter(state='pending',
            next_attempt_at__lte=timezone.now()).order_by('next_attempt_at').values_list('pk', flat=True)[:100])
        sent = sum(deliver_session_email(pk) for pk in ids)
        self.stdout.write(f'Checked {len(ids)} alerts; {sent} accepted by email provider.')
