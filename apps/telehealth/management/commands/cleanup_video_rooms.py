from datetime import timedelta
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from apps.appointments.models import Appointment
from apps.telehealth import provider
from apps.telehealth.access import enabled_for, agreements_ready, role_for, usable, fingerprint
from apps.telehealth.models import TelehealthRoom, VideoRuntime
from apps.telehealth.service import close_room


@transaction.atomic
def cleanup_one(pk):
    item = TelehealthRoom.objects.filter(pk=pk).values('appointment_id').first()
    if not item:
        return True
    appointment = Appointment.objects.select_for_update().select_related('practice', 'therapist__user').get(pk=item['appointment_id'])
    room = TelehealthRoom.objects.select_for_update().get(pk=pk)
    now = timezone.now()
    host = room.participants.select_related('user').filter(role='host').first()
    invalid_host = not host or host.state != 'admitted' or host.last_seen_at < now-timedelta(seconds=90)
    if host:
        try:
            role_for(host.user, appointment)
        except Exception:
            invalid_host = True
    if (not enabled_for(appointment.practice_id) or not agreements_ready(appointment.practice_id)
            or not usable(appointment, now) or room.status == 'closing'
            or fingerprint(appointment) != room.appointment_fingerprint
            or not room.expires_at or room.expires_at <= now or invalid_host):
        return close_room(room)
    patient = room.participants.select_related('user').filter(role='patient').exclude(state='left').first()
    if patient:
        try:
            role_for(patient.user, appointment)
            valid = patient.last_seen_at >= now-timedelta(seconds=90)
        except Exception:
            valid = False
        if not valid:
            provider.revoke_role(room, 'patient')
            patient.state = 'left'
            patient.save(update_fields=['state'])
    return True


class Command(BaseCommand):
    help = 'Run every minute. Close expired/revoked rooms and maintain the video safety heartbeat.'

    def handle(self, *args, **kwargs):
        failures = 0
        ids = list(TelehealthRoom.objects.filter(provider='chime').exclude(external_room_id='').values_list('pk', flat=True))
        for pk in ids:
            try:
                if not cleanup_one(pk):
                    failures += 1
            except Exception:
                failures += 1
        if failures:
            raise CommandError('Video cleanup needs attention; new video connections will fail closed.')
        VideoRuntime.objects.update_or_create(pk=1, defaults={'last_cleanup_at': timezone.now()})
        self.stdout.write('Video cleanup completed; safety heartbeat updated.')
