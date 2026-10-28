from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied
from django.db import transaction
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
from .forms import SupportReplyForm
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
