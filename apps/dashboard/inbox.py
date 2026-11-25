"""Live, read-only work queue. Source workflows remain authoritative."""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.core.paginator import Paginator
from django.db.models import CharField, F, Value
from django.db.models.functions import Coalesce, Concat
from django.urls import reverse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import TemplateView

from apps.accounts.access import (
    ClientPortalRedirectMixin, get_practice_for_user, has_practice_permission,
)
from apps.appointments.access import manages_sessions, scope_sessions
from apps.appointments.models import Appointment
from apps.clinical.models import SessionNote
from apps.portal.models import (
    ClientIntakeAssignment, ClientPortalRequest, PortalProfileSubmission, PublicBookingRequest,
)
from apps.practices.models import TherapistProfile


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


def pending_sources(user, therapist=''):
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
    if not therapist:
        return sources
    filtered = []
    for kind, queryset, occurred_at in sources:
        if kind in {'note', 'missing_note'}:
            assignee = F('therapist_id')
        elif kind in {'portal', 'booking'}:
            assignee = Coalesce('appointment__therapist_id', 'client__primary_therapist_id')
        else:
            assignee = F('client__primary_therapist_id')
        queryset = queryset.annotate(_inbox_assignee=assignee)
        lookup = ({'_inbox_assignee__isnull': True} if therapist == 'unassigned'
                  else {'_inbox_assignee': therapist})
        filtered.append((kind, queryset.filter(**lookup), occurred_at))
    return filtered


def therapist_filter(user, value):
    """Validate against the current practice and role, never broaden an invalid filter."""
    practice = get_practice_for_user(user)
    therapists = TherapistProfile.objects.filter(practice=practice) if practice else TherapistProfile.objects.none()
    if not manages_sessions(user):
        therapists = therapists.filter(user=user)
    choices = [
        {'value': str(therapist.pk), 'label': therapist.user.get_full_name() or therapist.user.username}
        for therapist in therapists.select_related('user').order_by('user__first_name', 'user__last_name', 'pk')
    ]
    if value not in {'', 'unassigned'} and value not in {choice['value'] for choice in choices}:
        raise Http404
    return choices


def inbox_summary(request):
    if not hasattr(request, '_pending_inbox_summary'):
        counts = {key: 0 for key in LABELS}
        for kind, queryset, _date in pending_sources(request.user):
            counts[KINDS[kind][0]] += queryset.count()
        request._pending_inbox_summary = counts
    return request._pending_inbox_summary


def pending_rows(user, category, therapist=''):
    sources = []
    for kind, queryset, occurred_at in pending_sources(user, therapist):
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
        url = reverse('pending_inbox_detail', args=[kind, pk])
    elif kind == 'note':
        url = (reverse('clinical:edit', args=[pk]) if has_practice_permission(user, 'clinical', 'edit')
               else reverse('pending_inbox_detail', args=[kind, pk]))
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
        therapist = self.request.GET.get('therapist', '')
        choices = therapist_filter(self.request.user, therapist)
        # Sidebar/Activities retain the overall queue; only this view's counts are filtered.
        if therapist:
            counts = {key: 0 for key in LABELS}
            for kind, queryset, _date in pending_sources(self.request.user, therapist):
                counts[KINDS[kind][0]] += queryset.count()
        else:
            counts = inbox_summary(self.request)
        page = Paginator(pending_rows(self.request.user, category, therapist), 25).get_page(self.request.GET.get('page'))
        context.update(
            category=category, pending_total=sum(counts.values()),
            therapist=therapist, therapist_choices=choices,
            categories=[dict(key=key, label=label, count=counts[key]) for key, label in LABELS.items()],
            page_obj=page, pending_items=[decorate_row(row, self.request.user) for row in page],
        )
        return context


@method_decorator(never_cache, name='dispatch')
class PendingInboxDetailView(LoginRequiredMixin, ClientPortalRedirectMixin, TemplateView):
    """Read a request or a read-only note; mutations use their original endpoints."""
    template_name = 'dashboard/inbox_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        kind = self.kwargs['kind']
        practice = get_practice_for_user(self.request.user)
        if kind in {'portal', 'booking'}:
            if not has_practice_permission(self.request.user, 'requests', 'view'):
                raise PermissionDenied
            model = PublicBookingRequest if kind == 'booking' else ClientPortalRequest
            record = get_object_or_404(model.objects.select_related('client', 'appointment'),
                                       practice=practice, pk=self.kwargs['pk'])
            context['can_act'] = has_practice_permission(self.request.user, 'requests', 'edit')
        elif kind == 'note':
            if not has_practice_permission(self.request.user, 'clinical', 'view'):
                raise PermissionDenied
            record = get_object_or_404(scope_sessions(SessionNote.objects.all(), self.request.user)
                .select_related('client', 'therapist__user', 'appointment'), pk=self.kwargs['pk'])
        else:
            raise Http404
        context.update(kind=kind, record=record)
        return context
