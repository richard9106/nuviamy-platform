"""Only opaque references and generic notices leave support storage by email."""
from django.conf import settings
from django.core.mail import EmailMessage
from apps.audit.models import AuditLog


def notify_support(ticket, *, customer=False):
    if customer and not ticket.requester_id:
        return
    recipient = ticket.requester.email if customer else settings.SUPPORT_EMAIL
    if not recipient:
        return
    body = ('There is an update to your NuviaMy support request. '
            'Sign in to NuviaMy and open Help > My support requests.' if customer else
            'A NuviaMy support request is waiting for review. Sign in to the platform admin.')
    try:
        EmailMessage(subject='NuviaMy support update', body=body,
                     from_email=settings.DEFAULT_FROM_EMAIL, to=[recipient]).send(fail_silently=False)
    except Exception:
        # Preserve the request; do not leak provider details or retry bodies by email.
        AuditLog.objects.create(practice=ticket.practice, actor=None,
            action=AuditLog.Action.UPDATE, object_type='dashboard.SupportTicket',
            object_id=str(ticket.pk), metadata={'event': 'support_notice_failed'})
