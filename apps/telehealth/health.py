"""Non-identifying operational status; no participant/media metadata is read."""
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from .models import TelehealthRoom, VideoRuntime


def video_health():
    if not settings.TELEHEALTH_ENABLED:
        return {'enabled': False}
    last = VideoRuntime.objects.filter(pk=1).values_list('last_cleanup_at', flat=True).first()
    age = timezone.now()-last if last else None
    return {'enabled': True,
            'cleanup_fresh': age is not None and timedelta(0) <= age <= timedelta(seconds=150),
            'revocations_clear': not TelehealthRoom.objects.filter(provider='chime', status='closing').exclude(external_room_id='').exists()}
