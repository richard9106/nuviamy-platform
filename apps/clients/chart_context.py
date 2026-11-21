from datetime import timedelta
from decimal import Decimal

from django.db.models import Q, Sum
from django.urls import reverse
from django.utils import timezone

from apps.appointments.access import scope_sessions
from apps.appointments.models import Appointment
from apps.billing.models import Invoice
from apps.portal.models import ClientIntakeAssignment
from .forms import AdministrativeNoteForm, ClientForm


def add_chart_context(context, request, client, permissions):
    context['client_edit_form'] = ClientForm(instance=client, practice=client.practice, auto_id='workspace-client-%s')
    context['administrative_note_form'] = AdministrativeNoteForm()
    context['profile_submissions'] = client.profile_submissions.filter(practice=client.practice)[:5]
    if permissions['billing']:
        invoices = Invoice.objects.filter(practice=client.practice, client=client,
            status__in=[Invoice.Status.SENT, Invoice.Status.OVERDUE]).annotate(
                chart_paid=Sum('payments__amount'),
                chart_insurance_paid=Sum('payments__amount', filter=Q(payments__method='insurance')))
        totals = {'client': Decimal('0'), 'insurance': Decimal('0'), 'total': Decimal('0'), 'count': 0}
        for invoice in invoices:
            paid = invoice.chart_paid or Decimal('0')
            balance = max(invoice.amount - paid, Decimal('0'))
            totals['total'] += balance
            totals['count'] += balance > 0
            if invoice.billing_type == 'insurance':
                insurance_paid = invoice.chart_insurance_paid or Decimal('0')
                totals['client'] += max((invoice.client_responsibility or Decimal('0')) - (paid - insurance_paid), Decimal('0'))
                totals['insurance'] += max(invoice.insurance_responsibility - insurance_paid, Decimal('0'))
            else:
                totals['client'] += balance
        context['chart_balances'] = totals
    assignments = ClientIntakeAssignment.objects.none()
    if permissions['intake']:
        assignments = ClientIntakeAssignment.objects.filter(practice=client.practice, client=client).select_related('template').defer('answers')
        context['client_form_assignments'] = assignments[:30]
        context['pending_forms_count'] = assignments.filter(status=ClientIntakeAssignment.Status.ASSIGNED).count()
        context['latest_form_delivery'] = client.form_deliveries.filter(practice=client.practice).order_by('-created_at').first()
    if context['workspace_tab'] != 'overview':
        if context['workspace_tab'] == 'measures' and permissions['clinical'] and permissions['intake']:
            from apps.portal.measures import chart_series
            records = list(assignments.filter(template_snapshot__measure_code__in=['phq9_en_v1', 'gad7_en_v1'])
                           .exclude(status=ClientIntakeAssignment.Status.ASSIGNED).defer(None)
                           .order_by('-submitted_at', '-pk')[:50])
            context['measure_series'] = chart_series(records)
            context['measure_history_count'] = len(records)
        return
    kind = request.GET.get('items', 'all')
    if kind not in ('all', 'administrative', 'appointments', 'forms'):
        kind = 'all'
    period = request.GET.get('period', 'all')
    if period not in ('all', '30', '90'):
        period = 'all'
    since = timezone.now() - timedelta(days=int(period)) if period != 'all' else None
    context.update(activity_kind=kind, activity_period=period)
    activity = []
    if kind in ('all', 'administrative'):
        notes = client.administrative_notes.filter(practice=client.practice).select_related('author')
        if since:
            notes = notes.filter(created_at__gte=since)
        for note in notes[:50]:
            activity.append({'kind': 'Administrative note', 'date': note.created_at,
                'title': note.author.get_full_name() or note.author.username, 'content': note.content})
    if permissions['appointments'] and kind in ('all', 'appointments'):
        sessions = scope_sessions(Appointment.objects.filter(practice=client.practice, client=client), request.user)
        if since:
            sessions = sessions.filter(starts_at__gte=since)
        for session in sessions.order_by('-starts_at')[:50]:
            activity.append({'kind': 'Appointment', 'date': session.starts_at,
                'title': session.get_appointment_type_display(), 'status': session.get_status_display(),
                'url': reverse('appointments:edit', args=[session.pk]) if permissions.get('appointments_edit') else ''})
    if permissions['intake'] and kind in ('all', 'forms'):
        if since:
            assignments = assignments.filter(created_at__gte=since)
        for assignment in assignments[:50]:
            activity.append({'kind': 'Client form', 'date': assignment.created_at, 'title': assignment.packet_name,
                'status': assignment.get_status_display(), 'url': reverse('intake:responses', args=[assignment.pk])})
    context['client_activity'] = sorted(activity, key=lambda item: item['date'], reverse=True)[:50]
