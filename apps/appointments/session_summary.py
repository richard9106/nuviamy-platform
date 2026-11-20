"""Batch metadata only; no note bodies or patient responses are fetched."""
from collections import Counter

from django.db.models import Count, Q

from apps.accounts.access import get_practice_for_user, has_practice_permission
from .access import scope_sessions
from .models import Appointment


def prepare_session_summaries(sessions, user):
    sessions = list(sessions)
    clinical = has_practice_permission(user, 'clinical', 'view')
    billing = has_practice_permission(user, 'billing', 'view')
    if not sessions or not has_practice_permission(user, 'appointments', 'view') or not (clinical or billing):
        return sessions
    practice = get_practice_for_user(user)
    allowed = set(scope_sessions(Appointment.objects.filter(pk__in=[s.pk for s in sessions]), user).values_list('pk', flat=True))
    selected = {s.pk: s for s in sessions if s.pk in allowed and s.practice_id == getattr(practice, 'pk', None)}
    if clinical:
        from apps.clinical.models import SessionNote
        for session in selected.values():
            session.note_summary = {'signed': 0, 'unsigned': 0}
        notes = scope_sessions(SessionNote.objects.filter(practice=practice, appointment_id__in=selected).exclude(note_type='treatment_plan'), user)
        for row in notes.values('appointment_id').annotate(total=Count('pk'), signed=Count('pk', filter=Q(signature__isnull=False))):
            selected[row['appointment_id']].note_summary = {'signed': row['signed'], 'unsigned': row['total'] - row['signed']}
    if billing:
        from apps.billing.models import Invoice
        for session in selected.values():
            session.invoice_summary = Counter()
        rows = Invoice.objects.filter(practice=practice, appointment_id__in=selected).values('appointment_id', 'status').annotate(total=Count('pk'))
        for row in rows:
            selected[row['appointment_id']].invoice_summary[row['status']] = row['total']
    return sessions
