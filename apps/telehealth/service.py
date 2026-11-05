"""Two authenticated participants, explicit admission, no persistent join tokens."""
from datetime import timedelta
import hashlib
import uuid

from django.conf import settings
from django.db import transaction
from django.http import Http404
from django.utils import timezone
from apps.appointments.models import Appointment
from . import provider
from .access import agreements_ready, enabled_for, fingerprint, role_for, usable
from .models import TelehealthRoom, VideoParticipant, VideoRuntime


class Unavailable(Exception):
    pass


def close_room(room):
    """Persist a closing fence even if AWS needs a retry; worker handles retries."""
    try:
        provider.terminate(room)
    except Exception:
        room.status = TelehealthRoom.Status.CLOSING
        room.save(update_fields=['status', 'updated_at'])
        return False
    room.status = TelehealthRoom.Status.ENDED
    room.meeting_payload = {}
    room.external_room_id = ''
    room.save(update_fields=['status', 'meeting_payload', 'external_room_id', 'updated_at'])
    room.participants.update(state=VideoParticipant.State.LEFT)
    return True


def session_hash(request):
    if not request.session.session_key:
        request.session.save()
    return hashlib.sha256(request.session.session_key.encode()).hexdigest()


def request_nonce(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Invalid browser session.') from None


def state(room, participant, role, now):
    other = room.participants.filter(role='patient', state='waiting', last_seen_at__gte=now-timedelta(seconds=30)).exists()
    return {'state': 'ended' if room.status in {'ended', 'cancelled', 'closing'} else (participant.state if participant else 'ready'),
            'waiting': bool(other) if role == 'host' else False,
            'expiresAt': room.expires_at.isoformat() if room.expires_at else None}


@transaction.atomic
def action(request, appointment_id, operation, nonce):
    appointment = Appointment.objects.select_for_update().select_related('practice', 'therapist__user').get(pk=appointment_id)
    role = role_for(request.user, appointment)
    if not enabled_for(appointment.practice_id) or not agreements_ready(appointment.practice_id):
        raise Http404
    now = timezone.now()
    current_fingerprint = fingerprint(appointment)
    room = TelehealthRoom.objects.select_for_update().filter(appointment=appointment).first()
    if room and room.provider != TelehealthRoom.Provider.CHIME:
        raise Http404
    if not usable(appointment, now):
        if room and room.external_room_id:
            close_room(room)
        return {'state': 'unavailable'}
    if room and room.appointment_fingerprint != current_fingerprint:
        if not close_room(room):
            return {'state': 'ended'}
        room.participants.all().delete()
        room.appointment_fingerprint = current_fingerprint
        room.status = TelehealthRoom.Status.CREATED
        room.expires_at = None
        room.save()
    if room and (room.status in {'ended', 'cancelled', 'closing'} or (room.expires_at and room.expires_at <= now)):
        if room.external_room_id:
            close_room(room)
        return {'state': 'ended'}
    if operation not in {'join', 'heartbeat', 'admit', 'leave', 'end'}:
        raise ValueError('Invalid action.')
    if operation in {'admit', 'end'} and role != 'host':
        raise Http404
    if not room and operation != 'join':
        return {'state': 'ready', 'waiting': False}
    if room is None:
        room = TelehealthRoom.objects.create(practice=appointment.practice, appointment=appointment,
            provider=TelehealthRoom.Provider.CHIME, appointment_fingerprint=current_fingerprint)
    participants = room.participants.select_for_update()
    participant = participants.filter(role=role).first()
    identity = session_hash(request)
    matches = bool(participant and participant.user_id == request.user.pk
                   and participant.browser_nonce == nonce and participant.session_hash == identity)
    if operation == 'end':
        close_room(room)
        return {'state': 'ended'}
    if operation == 'leave':
        if matches:
            provider.revoke_role(room, role)
            participant.state = VideoParticipant.State.LEFT
            participant.save(update_fields=['state'])
        return {'state': 'left'}
    if operation == 'admit':
        if not matches or participant.state != 'admitted' or not room.external_room_id:
            raise Http404
        waiting = participants.filter(role='patient', state='waiting', last_seen_at__gte=now-timedelta(seconds=30)).first()
        if waiting:
            waiting.state = 'admitted'
            waiting.save(update_fields=['state'])
        return state(room, participant, role, now)
    if operation == 'heartbeat':
        if not matches:
            return {'state': 'superseded'}
        runtime = VideoRuntime.objects.get(pk=1)
        if not runtime.last_cleanup_at or now-runtime.last_cleanup_at > timedelta(seconds=150):
            close_room(room)
            return {'state': 'ended'}
        participant.last_seen_at = now
        participant.save(update_fields=['last_seen_at'])
        return state(room, participant, role, now)
    runtime = VideoRuntime.objects.select_for_update().get(pk=1)
    if not runtime.last_cleanup_at or now-runtime.last_cleanup_at > timedelta(seconds=150):
        raise Unavailable
    if not matches:
        if participant:
            provider.revoke_role(room, role)
        participant, _ = VideoParticipant.objects.update_or_create(room=room, role=role, defaults={
            'user': request.user, 'state': 'admitted' if role == 'host' else 'waiting',
            'browser_nonce': nonce, 'session_hash': identity, 'last_seen_at': now, 'last_issued_at': None})
    elif participant.state == 'left':
        participant.state = 'admitted' if role == 'host' else 'waiting'
        participant.save(update_fields=['state'])
    if role == 'patient' and participant.state != 'admitted':
        return state(room, participant, role, now)
    if participant.last_issued_at and now-participant.last_issued_at < timedelta(seconds=2):
        return {'state': 'retry'}
    if not room.external_room_id:
        # Only the host can create a billable meeting; a waiting patient creates no AWS resources.
        if role != 'host':
            return {'state': 'waiting'}
        active = TelehealthRoom.objects.filter(provider='chime').exclude(external_room_id='').count()
        if active >= settings.TELEHEALTH_MAX_CONCURRENT_ROOMS:
            raise Unavailable
        room.control_region = settings.TELEHEALTH_CONTROL_REGION
        room.meeting_payload = provider.create(room.control_region, settings.TELEHEALTH_MEDIA_REGION, current_fingerprint)
        room.external_room_id = room.meeting_payload['MeetingId']
        room.expires_at = min(appointment.ends_at+timedelta(minutes=settings.TELEHEALTH_END_GRACE_MINUTES),
                              now+timedelta(minutes=settings.TELEHEALTH_MAX_SESSION_MINUTES))
        room.status = TelehealthRoom.Status.ACTIVE
        room.save()
    # JoinToken is sent only to this authenticated browser, never stored or logged.
    try:
        attendee = provider.issue(room, role)
    except Exception as error:
        if provider.absent(error):
            close_room(room)
            return {'state': 'ended'}
        # Keep the meeting reference committed so the worker can revoke it even
        # if CreateAttendee succeeded but its response was lost.
        return {'error': 'video_temporarily_unavailable'}
    participant.last_issued_at = now
    participant.last_seen_at = now
    participant.save(update_fields=['last_issued_at', 'last_seen_at'])
    return {'state': 'joined', 'Meeting': room.meeting_payload, 'Attendee': attendee,
            'expiresAt': room.expires_at.isoformat()}
