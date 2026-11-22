"""Live, read-only work queue. Source workflows remain authoritative."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.db.models import CharField, F, Value
from django.db.models.functions import Coalesce, Concat
from django.urls import reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from apps.accounts.access import (
    ClientPortalRedirectMixin, get_practice_for_user, has_practice_permission,
)
from apps.appointments.access import scope_sessions
from apps.appointments.models import Appointment
from apps.clinical.models import SessionNote
from apps.portal.models import (
    ClientIntakeAssignment, ClientPortalRequest, PortalProfileSubmission, PublicBookingRequest,
)


LABELS = {
    'forms': 'Forms to review',
    'information': 'Client information',
    'requests': 'Client requests',
    'notes': 'Session documentation',
}
KINDS = {
    'form': ('forms', 'Submitted form', 'Review responses'),
    'information': ('information', 'Updated client information', 'Review changes'),
    'portal': ('requests', 'Open portal request', 'Review request'),
    'booking': ('requests', 'Appointment request', 'Review booking'),
    'note': ('notes', 'Unsigned session note', 'Open note'),
    'missing_note': ('notes', 'Completed session without a note', 'Create note'),
}


def pending_sources(user):
    practice = get_practice_for_user(user)
    if not practice:
        return []
    can = lambda resource, action='view': has_practice_permission(user, resource, action)
    sources = []
    if can('intake') and can('clinical'):
        sources.append(('form', ClientIntakeAssignment.objects.filter(
            practice=practice, status='submitted'), Coalesce('submitted_at', 'created_at')))
    if can('clients', 'edit'):
        sources.append(('information', PortalProfileSubmission.objects.filter(
            practice=practice, status='pending'), F('created_at')))
    if can('requests'):
        sources.extend([
            ('portal', ClientPortalRequest.objects.filter(
                practice=practice, status__in=['new', 'reviewed']), F('created_at')),
            ('booking', PublicBookingRequest.objects.filter(
                practice=practice, status='pending'), F('created_at')),
        ])
    if can('clinical'):
        sources.append(('note', scope_sessions(SessionNote.objects.filter(is_locked=False), user), F('created_at')))
        if can('clinical', 'create') and can('appointments'):
            sources.append(('missing_note', scope_sessions(Appointment.objects.filter(
                status=Appointment.Status.COMPLETED, ends_at__lte=timezone.now(),
                session_notes__isnull=True), user), F('ends_at')))
    return sources


def inbox_summary(request):
    if not hasattr(request, '_pending_inbox_summary'):
        counts = {key: 0 for key in LABELS}
        for kind, queryset, _date in pending_sources(request.user):
            counts[KINDS[kind][0]] += queryset.count()
        request._pending_inbox_summary = counts
    return request._pending_inbox_summary


def pending_rows(user, category):
    sources = []
    for kind, queryset, occurred_at in pending_sources(user):
        if category and KINDS[kind][0] != category:
            continue
        prefix = '' if kind == 'booking' else 'client__'
        # Select metadata only: no clinical answers, message bodies or encrypted details.
        sources.append(queryset.order_by().annotate(
            item_id=F('pk'), occurred_at=occurred_at,
            item_kind=Value(kind, output_field=CharField()),
            person_name=Concat(prefix + 'first_name', Value(' '), prefix + 'last_name'),
            person_id=F('client_id'),
        ).values('item_id', 'occurred_at', 'item_kind', 'person_name', 'person_id'))
    if not sources:
        return []
    return sources[0].union(*sources[1:], all=True).order_by('occurred_at', 'item_kind', 'item_id')


def decorate_row(row, user):
    kind, pk = row['item_kind'], row['item_id']
    category, title, action = KINDS[kind]
    if kind == 'form':
        url = reverse('intake:responses', args=[pk])
    elif kind == 'information':
        url = reverse('clients:profile_submission', args=[row['person_id'], pk])
    elif kind in {'portal', 'booking'}:
        source = 'public' if kind == 'booking' else 'portal'
        url = reverse('portal_requests:list') + f'?source={source}&item={pk}'
    elif kind == 'note':
        url = (reverse('clinical:edit', args=[pk]) if has_practice_permission(user, 'clinical', 'edit')
               else reverse('clinical:list') + f'?client={row["person_id"]}&status=draft')
    else:
        url = reverse('clinical:create') + f'?appointment={pk}'
    client_url = (reverse('clients:detail', args=[row['person_id']])
                  if row['person_id'] and has_practice_permission(user, 'clients', 'view') else '')
    return dict(row, category=category, title=title, action=action, url=url, client_url=client_url)


@method_decorator(never_cache, name='dispatch')
class PendingInboxView(LoginRequiredMixin, ClientPortalRedirectMixin, TemplateView):
    template_name = 'dashboard/inbox.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = self.request.GET.get('type', '')
        category = category if category in LABELS else ''
        counts = inbox_summary(self.request)
        page = Paginator(pending_rows(self.request.user, category), 25).get_page(self.request.GET.get('page'))
        context.update(
            category=category, pending_total=sum(counts.values()),
            categories=[dict(key=key, label=label, count=counts[key]) for key, label in LABELS.items()],
            page_obj=page, pending_items=[decorate_row(row, self.request.user) for row in page],
        )
        return context
