"""Opt-in therapist email alerts using the configured transactional email backend."""
import hashlib
import uuid

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta

from apps.accounts.access import has_practice_permission, is_client_user
from apps.accounts.models import UserProfile
from .models import Appointment, SessionEmailNotification

REQUEST_KINDS = {'cancellation_request', 'reschedule_request'}
MAX_ATTEMPTS = 5


def eligible_profile(appointment, kind):
    user = appointment.therapist.user
    profile = UserProfile.objects.filter(user=user, practice_id=appointment.practice_id).first()
    if (not profile or not user.is_active or not user.email or is_client_user(user)
            or appointment.therapist.practice_id != appointment.practice_id
            or appointment.client.practice_id != appointment.practice_id
            or not has_practice_permission(user, 'appointments', 'view')):
        return None
    preference = 'request_email_notifications' if kind in REQUEST_KINDS else 'session_email_notifications'
    if not getattr(profile, preference):
        return None
    if kind in REQUEST_KINDS and not has_practice_permission(user, 'requests', 'view'):
        return None
    return profile


def queue_session_email(appointment, kind, *, portal_request=None, event_id=None):
    if not eligible_profile(appointment, kind):
        return
    if portal_request and (portal_request.practice_id != appointment.practice_id
            or portal_request.client_id != appointment.client_id):
        return
    identity = (f'request:{portal_request.pk}' if portal_request else
                f'appointment:{appointment.pk}:{event_id or uuid.uuid4()}')
    key = hashlib.sha256(f'{identity}:{kind}:{appointment.therapist.user_id}'.encode()).hexdigest()
    notification, created = SessionEmailNotification.objects.get_or_create(
        event_key=key, defaults=dict(practice_id=appointment.practice_id,
            recipient_id=appointment.therapist.user_id, appointment=appointment,
            portal_request=portal_request, kind=kind))
    if created:
        # A rollback also rolls back the outbox; nothing is sent before commit.
        transaction.on_commit(lambda: deliver_session_email(notification.pk), robust=True)


def deliver_session_email(pk):
    """Serialize workers. Recheck opt-in/access/current assignment before every send.

    Provider acceptance is not delivery confirmation. SMTP/SES has no exactly-once
    guarantee if the process dies after acceptance and before the database commit.
    """
    with transaction.atomic():
        notification = (SessionEmailNotification.objects.select_for_update(of=('self',))
            .select_related('appointment__therapist__user', 'appointment__client', 'portal_request')
            .filter(pk=pk).first())
        if not notification or notification.state != 'pending' or notification.next_attempt_at > timezone.now():
            return False
        appointment = notification.appointment
        profile = eligible_profile(appointment, notification.kind)
        portal_request = notification.portal_request
        expired = notification.created_at < timezone.now() - timedelta(hours=24)
        if (expired or not profile or notification.practice_id != appointment.practice_id
                or notification.recipient_id != profile.user_id
                or (portal_request and (portal_request.status == 'resolved'
                    or portal_request.appointment_id != appointment.pk
                    or portal_request.practice_id != appointment.practice_id
                    or portal_request.client_id != appointment.client_id))):
            notification.state = 'skipped'
            notification.save(update_fields=['state'])
            return False
        title = notification.get_kind_display()
        explanation = ('This is a request for your practice to review. The session has not been changed automatically.'
                       if notification.kind in REQUEST_KINDS else
                       'There is an update to a session assigned to you. Sign in to review the current details.')
        path = reverse('portal_requests:list') if portal_request else reverse('appointments:edit', args=[appointment.pk])
        context = {'title': title, 'explanation': explanation,
                   'review_url': settings.NOTIFICATION_SITE_URL + path,
                   'preferences_url': settings.NOTIFICATION_SITE_URL + reverse('profile_settings')}
        body = (f"{title}\n\n{explanation}\n\nReview in NuviaMy: {context['review_url']}\n\n"
                f"Manage email alerts: {context['preferences_url']}\n\n"
                'For privacy, this email contains no client names, session times or clinical details. '
                'Do not reply with personal health information.')
        notification.attempts += 1
        try:
            sent = send_mail('NuviaMy: ' + title, body, settings.DEFAULT_FROM_EMAIL,
                [profile.user.email], fail_silently=False,
                html_message=render_to_string('appointments/emails/session_alert.html', context)) == 1
        except Exception:
            # Never persist provider exception text: it may contain addresses or message data.
            sent = False
        if sent:
            notification.state = 'sent'
            notification.sent_at = timezone.now()
        elif notification.attempts >= MAX_ATTEMPTS:
            notification.state = 'failed'
        else:
            notification.next_attempt_at = timezone.now() + timedelta(minutes=2 ** notification.attempts)
        notification.save(update_fields=['state', 'attempts', 'sent_at', 'next_attempt_at'])
        return sent
