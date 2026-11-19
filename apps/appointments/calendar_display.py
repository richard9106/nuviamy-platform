"""Display-only calendar timing; never changes appointment status."""
from datetime import timedelta


def calendar_phase(appointment, now):
    if appointment.status in {'cancelled', 'no_show'}:
        return appointment.status
    if appointment.ends_at <= now:
        return 'past'
    if appointment.starts_at <= now + timedelta(hours=24):
        return 'soon'
    return 'future'
