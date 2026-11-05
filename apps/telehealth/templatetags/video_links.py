from django import template
from django.urls import reverse
from django.utils import timezone
from apps.telehealth.access import enabled_for, role_for
register = template.Library()


@register.simple_tag
def video_room_link(appointment, user):
    if not appointment or not enabled_for(appointment.practice_id):
        return ''
    if (appointment.appointment_type != 'video' or appointment.meeting_url
            or appointment.status != 'scheduled' or appointment.ends_at <= timezone.now()):
        return ''
    try:
        role_for(user, appointment)
    except Exception:
        return ''
    return reverse('telehealth:room', args=[appointment.pk])
