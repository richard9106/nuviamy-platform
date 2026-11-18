from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.utils.functional import cached_property
from django.views.decorators.cache import never_cache
from django.views.generic import ListView, FormView

from apps.accounts.access import get_practice_for_user, is_client_user
from apps.audit.models import AuditLog
from apps.audit.utils import log_audit_event
from apps.rate_limit import PostRateLimitMixin
from .forms import SupportReplyForm, SupportStatusForm
from .models import SupportTicket, SupportMessage
from .support_requests import notify_support


class SupportWorkspaceMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and (is_client_user(request.user)
                or not get_practice_for_user(request.user)):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def tickets(self):
        return SupportTicket.objects.filter(requester=self.request.user,
            practice=get_practice_for_user(self.request.user))


@method_decorator(never_cache, name='dispatch')
class SupportTicketListView(SupportWorkspaceMixin, ListView):
    template_name = 'support/requests.html'
    context_object_name = 'tickets'
    paginate_by = 20

    def get_queryset(self):
        return self.tickets().defer('contact_name', 'contact_email')


@method_decorator(never_cache, name='dispatch')
class SupportTicketDetailView(SupportWorkspaceMixin, PostRateLimitMixin, FormView):
    template_name = 'support/request_detail.html'
    form_class = SupportReplyForm
    rate_limit_scope = 'support-reply'
    rate_limit_count = 20
    rate_limit_seconds = 3600

    @cached_property
    def ticket(self):
        return get_object_or_404(self.tickets(), pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        return super().get_context_data(ticket=self.ticket,
            thread_messages=self.ticket.messages.all(), **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        self.ticket = get_object_or_404(self.tickets().select_for_update(), pk=self.ticket.pk)
        if self.ticket.status == SupportTicket.Status.CLOSED:
            form.add_error(None, 'This request is closed. Create a new request if you still need help.')
            return self.form_invalid(form)
        message = SupportMessage.objects.create(ticket=self.ticket, author=self.request.user,
                                      body=form.cleaned_data['message'])
        log_audit_event(self.request, AuditLog.Action.CREATE, 'dashboard.SupportMessage',
            message.pk, practice=self.ticket.practice, metadata={'event': 'support_reply'})
        transaction.on_commit(lambda: notify_support(self.ticket))
        return redirect(reverse('support_request_detail', args=[self.ticket.pk]))


class SupportOperatorMixin(LoginRequiredMixin):
    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not (request.user.is_active and request.user.is_superuser):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)


@method_decorator(never_cache, name='dispatch')
class SupportInboxView(SupportOperatorMixin, ListView):
    template_name = 'support/inbox.html'
    context_object_name = 'tickets'
    paginate_by = 20

    def get_queryset(self):
        self.selected_status = self.request.GET.get('status', SupportTicket.Status.OPEN)
        if self.selected_status not in {'all', *SupportTicket.Status.values}:
            self.selected_status = SupportTicket.Status.OPEN
        self.selected_topic = self.request.GET.get('topic', '')
        if self.selected_topic not in SupportTicket.Topic.values:
            self.selected_topic = ''
        latest = SupportMessage.objects.filter(ticket=OuterRef('pk')).order_by('-created_at', '-pk')
        tickets = SupportTicket.objects.select_related('practice').defer('contact_email').annotate(
            latest_at=Subquery(latest.values('created_at')[:1]),
            latest_is_operator=Subquery(latest.values('is_operator')[:1]),
        )
        if self.selected_status != 'all':
            tickets = tickets.filter(status=self.selected_status)
        if self.selected_topic:
            tickets = tickets.filter(topic=self.selected_topic)
        return tickets.order_by('-latest_at', '-created_at', 'pk')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        counts = SupportTicket.objects.aggregate(
            total=Count('pk'), open=Count('pk', filter=Q(status=SupportTicket.Status.OPEN)),
            closed=Count('pk', filter=Q(status=SupportTicket.Status.CLOSED)),
        )
        context.update(counts=counts, selected_status=self.selected_status,
                       selected_topic=self.selected_topic, topics=SupportTicket.Topic.choices)
        return context


@method_decorator(never_cache, name='dispatch')
class SupportInboxDetailView(SupportOperatorMixin, PostRateLimitMixin, FormView):
    template_name = 'support/inbox_detail.html'
    form_class = SupportReplyForm
    rate_limit_scope = 'operator-support'
    rate_limit_count = 60
    rate_limit_seconds = 3600

    @cached_property
    def ticket(self):
        return get_object_or_404(SupportTicket.objects.select_related('practice', 'requester'),
                                 pk=self.kwargs['pk'])

    def get_context_data(self, **kwargs):
        return super().get_context_data(ticket=self.ticket,
            thread_messages=self.ticket.messages.all(), **kwargs)

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.ticket = get_object_or_404(SupportTicket.objects.select_for_update(), pk=kwargs['pk'])
        action = request.POST.get('action')
        if action == 'status':
            status_form = SupportStatusForm(request.POST)
            if not status_form.is_valid():
                form = self.get_form()
                form.add_error(None, 'Choose a valid request status.')
                return self.form_invalid(form)
            previous_status = self.ticket.status
            self.ticket.status = status_form.cleaned_data['status']
            if previous_status != self.ticket.status:
                self.ticket.save(update_fields=['status'])
                log_audit_event(request, AuditLog.Action.UPDATE, 'dashboard.SupportTicket',
                    self.ticket.pk, practice=self.ticket.practice, platform=True,
                    metadata={'event': 'operator_support_status', 'from': previous_status,
                              'to': self.ticket.status})
            messages.success(request, 'Request status updated.')
        elif action == 'reply':
            form = self.get_form()
            if not form.is_valid():
                return self.form_invalid(form)
            if self.ticket.status == SupportTicket.Status.CLOSED:
                form.add_error(None, 'Reopen this request before replying.')
                return self.form_invalid(form)
            if not self.ticket.requester_id:
                form.add_error(None, 'This sender has no linked account. Use their contact email to follow up.')
                return self.form_invalid(form)
            reply = SupportMessage.objects.create(ticket=self.ticket, author=request.user,
                is_operator=True, body=form.cleaned_data['message'])
            log_audit_event(request, AuditLog.Action.CREATE, 'dashboard.SupportMessage',
                reply.pk, practice=self.ticket.practice, platform=True,
                metadata={'event': 'operator_support_reply'})
            transaction.on_commit(lambda: notify_support(self.ticket, customer=True))
            messages.success(request, "Reply saved in the requester's support conversation.")
        else:
            form = self.get_form()
            form.add_error(None, 'Choose an available action.')
            return self.form_invalid(form)
        return redirect('staff_support_detail', pk=self.ticket.pk)
