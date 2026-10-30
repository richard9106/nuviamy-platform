"""Track persisted session changes, including series and public-booking saves."""
import uuid

from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver

from .models import Appointment, SessionEmailNotification
from .notifications import queue_session_email

FIELDS = ('starts_at', 'ends_at', 'status', 'therapist_id', 'appointment_type')


@receiver(pre_save, sender=Appointment)
def remember_session_state(sender, instance, raw=False, **kwargs):
    if not raw:
        instance._notification_event_id = uuid.uuid4()
        instance._notification_previous = (sender.objects.filter(pk=instance.pk).values(*FIELDS).first()
                                            if instance.pk else None)


@receiver(post_save, sender=Appointment)
def notify_session_change(sender, instance, created, raw=False, **kwargs):
    if raw:
        return
    # Read persisted state, not unsaved attributes excluded by update_fields.
    current = sender.objects.select_related('therapist__user', 'client').get(pk=instance.pk)
    before = getattr(instance, '_notification_previous', None)
    if created:
        kind = SessionEmailNotification.Kind.CREATED
    elif not before or not any(before[field] != getattr(current, field) for field in FIELDS):
        return
    else:
        kind = (SessionEmailNotification.Kind.CANCELLED if current.status == Appointment.Status.CANCELLED
                and before['status'] != Appointment.Status.CANCELLED else SessionEmailNotification.Kind.UPDATED)
    queue_session_email(current, kind, event_id=getattr(instance, '_notification_event_id', None))


@receiver(post_save, sender='portal.ClientPortalRequest')
def notify_client_change_request(sender, instance, created, raw=False, **kwargs):
    if raw or not created or not instance.appointment_id:
        return
    kinds = {'cancellation': SessionEmailNotification.Kind.CANCELLATION_REQUEST,
             'reschedule': SessionEmailNotification.Kind.RESCHEDULE_REQUEST}
    kind = kinds.get(instance.category)
    if kind and instance.status == 'new':
        queue_session_email(instance.appointment, kind, portal_request=instance)
