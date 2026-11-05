from datetime import timedelta
import hashlib
import json

from django.conf import settings
from django.http import Http404
from django.utils import timezone
from apps.accounts.access import get_practice_for_user, has_practice_permission
from apps.accounts.contract_models import StandardAgreementAcceptance, ClinicalContractSignature
from apps.accounts.standard_agreements import AGREEMENT_VERSION
from apps.billing.access import subscription_access
from apps.appointments.models import Appointment


def enabled_for(practice_id):
    return settings.TELEHEALTH_ENABLED and practice_id in settings.TELEHEALTH_PRACTICE_IDS


def agreements_ready(practice_id):
    return (StandardAgreementAcceptance.objects.filter(practice_id=practice_id, version=AGREEMENT_VERSION).exists()
            or ClinicalContractSignature.objects.filter(bundle__request__practice_id=practice_id).exists())


def role_for(user, appointment):
    if not user.is_active:
        raise Http404
    portal = getattr(user, 'client_portal_access', None)
    if portal:
        if (portal.is_active and portal.practice_id == appointment.practice_id
                and portal.client_id == appointment.client_id):
            return 'patient'
        raise Http404
    profile = getattr(user, 'nuvia_profile', None)
    if (profile and profile.role in {'owner', 'admin', 'therapist'}
            and get_practice_for_user(user).pk == appointment.practice_id
            and appointment.therapist.user_id == user.pk
            and has_practice_permission(user, 'appointments', 'view')):
        return 'host'
    raise Http404


def usable(appointment, now=None):
    now = now or timezone.now()
    return (appointment.status == Appointment.Status.SCHEDULED
            and appointment.appointment_type == Appointment.AppointmentType.VIDEO
            and not appointment.meeting_url
            and appointment.therapist.user.is_active
            and subscription_access(appointment.practice)['mode'] in {'full', 'grace'}
            and appointment.starts_at-timedelta(minutes=settings.TELEHEALTH_EARLY_JOIN_MINUTES) <= now
            < appointment.ends_at+timedelta(minutes=settings.TELEHEALTH_END_GRACE_MINUTES))


def fingerprint(appointment):
    values = [appointment.pk, appointment.practice_id, appointment.client_id, appointment.therapist_id,
              appointment.starts_at.isoformat(), appointment.ends_at.isoformat(),
              appointment.status, appointment.appointment_type, appointment.meeting_url]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()
