from django import template
from django.urls import reverse
from django.utils import timezone
from apps.telehealth.access import enabled_for, role_for
register = template.Library()


@register.simple_tag(takes_context=True)
def video_room_link(context, appointment, user):
    if not appointment:
        return ''
    request=context.get('request')
    cache=getattr(request,'_video_link_availability',{})
    if appointment.practice_id not in cache:
        cache[appointment.practice_id]=enabled_for(appointment.practice_id)
    if request is not None:
        request._video_link_availability=cache
    if not cache[appointment.practice_id]:
        return ''
    if (appointment.appointment_type != 'video' or appointment.meeting_url
            or appointment.status != 'scheduled' or appointment.ends_at <= timezone.now()):
        return ''
    try:
        role_for(user, appointment)
    except Exception:
        return ''
    return reverse('telehealth:room', args=[appointment.pk])
