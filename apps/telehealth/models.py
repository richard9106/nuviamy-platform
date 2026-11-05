from django.core.exceptions import ValidationError
from django.db import models
from django.conf import settings
import uuid


class TelehealthRoom(models.Model):
    class Provider(models.TextChoices):
        MANUAL = "manual", "Manual Link"
        ZOOM = "zoom", "Zoom"
        DAILY = "daily", "Daily"
        TWILIO = "twilio", "Twilio"
        CHIME = 'chime', 'NuviaMy video'

    class Status(models.TextChoices):
        CREATED = "created", "Created"
        ACTIVE = "active", "Active"
        ENDED = "ended", "Ended"
        CANCELLED = "cancelled", "Cancelled"
        CLOSING = 'closing', 'Closing'

    practice = models.ForeignKey("practices.Practice", on_delete=models.CASCADE, related_name="telehealth_rooms")
    appointment = models.OneToOneField("appointments.Appointment", on_delete=models.CASCADE, related_name="telehealth_room")
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.MANUAL)
    join_url = models.URLField(blank=True)
    host_url = models.URLField(blank=True)
    external_room_id = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.CREATED)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    appointment_fingerprint = models.CharField(max_length=64, blank=True)
    meeting_payload = models.JSONField(default=dict, blank=True)
    control_region = models.CharField(max_length=30, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    def clean(self):
        if self.appointment_id and self.practice_id and self.appointment.practice_id != self.practice_id:
            raise ValidationError({"appointment": "Telehealth appointment must belong to the same practice."})
        if self.appointment_id and self.appointment.appointment_type != self.appointment.AppointmentType.VIDEO:
            raise ValidationError({"appointment": "Telehealth rooms can only be attached to video appointments."})
        if self.provider != self.Provider.CHIME and not self.join_url:
            raise ValidationError({'join_url': 'Enter the external video link.'})

    def __str__(self):
        return f"{self.get_provider_display()} room for {self.appointment}"


class VideoParticipant(models.Model):
    class Role(models.TextChoices):
        HOST = 'host', 'Therapist'
        PATIENT = 'patient', 'Patient'

    class State(models.TextChoices):
        WAITING = 'waiting', 'Waiting'
        ADMITTED = 'admitted', 'Admitted'
        LEFT = 'left', 'Left'

    room = models.ForeignKey(TelehealthRoom, on_delete=models.CASCADE, related_name='participants')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.CharField(max_length=10, choices=Role.choices)
    state = models.CharField(max_length=12, choices=State.choices, default=State.WAITING)
    browser_nonce = models.UUIDField(default=uuid.uuid4)
    session_hash = models.CharField(max_length=64)
    last_seen_at = models.DateTimeField()
    last_issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['room', 'role'], name='one_video_participant_per_role')]


class VideoRuntime(models.Model):
    """Singleton lock for capacity and evidence that the cleanup worker is alive."""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_cleanup_at = models.DateTimeField(null=True, blank=True)
