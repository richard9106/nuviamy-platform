"""Revoke live rooms on committed schedule/assignment changes, not just in the UI."""
from django.db import transaction
from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver
from django.db.models.deletion import ProtectedError
from apps.appointments.models import Appointment
from .access import fingerprint
from .models import TelehealthRoom
from .service import close_room


@transaction.atomic
def invalidate_appointment(pk):
    appointment = Appointment.objects.select_for_update().filter(pk=pk).first()
    if not appointment:
        return
    room = TelehealthRoom.objects.select_for_update().filter(appointment_id=pk, provider='chime').exclude(external_room_id='').first()
    if room and room.appointment_fingerprint != fingerprint(appointment):
        close_room(room)


@receiver(post_save, sender=Appointment)
def schedule_changed(sender, instance, **kwargs):
    if kwargs.get('raw'):
        return
    transaction.on_commit(lambda pk=instance.pk: invalidate_appointment(pk))


@receiver(pre_delete, sender=TelehealthRoom)
def room_deleted(sender, instance, **kwargs):
    if instance.provider == 'chime' and instance.external_room_id and not close_room(instance):
        raise ProtectedError('End the video session before deleting its appointment.', [instance])
