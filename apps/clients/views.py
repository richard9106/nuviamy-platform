from apps.appointments.access import scope_sessions
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from django.db.models.deletion import ProtectedError
from django.db.models import Q, Sum, Value
from django.db.models.functions import Concat
from decimal import Decimal
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.accounts.access import ClientPortalRedirectMixin, PracticePermissionMixin, get_practice_for_user, has_practice_permission
from apps.clinical.forms import DiagnosisForm
from apps.appointments.models import Appointment
from apps.billing.models import Invoice, ServicePackage
from apps.clinical.models import Diagnosis, SessionNote, TreatmentPlan
from apps.documents.models import ClientDocument
from apps.portal.models import ClientPortalAccess
from .forms import ClientForm
from .models import Client


class PracticeContextMixin(ClientPortalRedirectMixin):
    def get_practice(self):
        return get_practice_for_user(self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['practice'] = self.get_practice()
        from apps.billing.insurance import available_payers
        context['insurance_payers'] = available_payers(context['practice'])
        return context


class ClientListView(LoginRequiredMixin, PracticePermissionMixin, PracticeContextMixin, ListView):
    permission_resource = 'clients'
    model = Client
    template_name = 'clients/list.html'
    context_object_name = 'clients'
    paginate_by = 25

    def get_queryset(self):
        practice = self.get_practice()
        if not practice:
            return Client.objects.none()

        queryset = (
            Client.objects.filter(practice=practice)
            .select_related('primary_therapist__user', 'insurance_payer')
            .order_by('last_name', 'first_name')
        )
        query = self.request.GET.get('q', '').strip()[:160]
        if query:
            queryset = queryset.annotate(search_name=Concat('first_name', Value(' '), 'last_name')).filter(
                Q(search_name__icontains=query) | Q(email__icontains=query) | Q(phone__icontains=query))
        status = self.request.GET.get('status', '')
        if status in Client.Status.values:
            queryset = queryset.filter(status=status)
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        practice = self.get_practice()
        context['client_therapists'] = practice.therapists.select_related('user') if practice else []
        context['note_appointments'] = scope_sessions(practice.appointments.select_related('client', 'therapist__user'), self.request.user) if practice else []
        context['billing_templates'] = practice.session_package_templates.filter(active=True) if practice else []
        context['billing_today'] = timezone.localdate()
        context['client_create_form'] = ClientForm(practice=practice, auto_id='client-create-%s')
        context['client_search'] = self.request.GET.get('q', '').strip()[:160]
        context['client_status'] = self.request.GET.get('status', '')
        return context


class ClientDetailView(LoginRequiredMixin, PracticePermissionMixin, PracticeContextMixin, DetailView):
    permission_resource = 'clients'
    model = Client
    template_name = 'clients/detail.html'
    context_object_name = 'client'

    def get_queryset(self):
        practice = self.get_practice()
        if not practice:
            return Client.objects.none()
        return Client.objects.filter(practice=practice).select_related('primary_therapist__user', 'insurance_payer')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        client = self.object
        permissions = {resource: has_practice_permission(self.request.user, resource, 'view')
                       for resource in ('appointments', 'clinical', 'billing', 'documents', 'intake')}
        allowed_tabs = {'overview'} | {tab for tab in ('clinical', 'billing', 'documents') if permissions[tab]}
        if permissions['intake']:
            allowed_tabs.add('forms')
        requested_tab = self.request.GET.get('tab', 'overview')
        if self.request.method == 'POST' and self.request.POST.get('return_to_patient') == '1':
            requested_tab = 'clinical'
        active_tab = requested_tab if requested_tab in allowed_tabs else 'overview'
        context.update({
            'workspace_tab': active_tab,
        })
        if has_practice_permission(self.request.user, 'clients', 'edit'):
            context['client_therapists'] = client.practice.therapists.select_related('user')
        if permissions['appointments']:
            appointments = scope_sessions(Appointment.objects.filter(client=client, practice=client.practice), self.request.user).select_related('therapist__user')
            consultations = appointments.filter(session_kind=Appointment.SessionKind.INITIAL_CONSULTATION)
            consultation = (consultations.filter(status=Appointment.Status.COMPLETED).order_by('-ends_at').first()
                            or consultations.filter(status=Appointment.Status.SCHEDULED).order_by('starts_at').first()
                            or consultations.order_by('-starts_at').first())
            context['initial_consultation'] = consultation
            if consultation and permissions['clinical']:
                context['initial_consultation_note'] = SessionNote.objects.filter(practice=client.practice, client=client, appointment=consultation).exclude(note_type='treatment_plan').order_by('-created_at').first()
            now = timezone.now()
            context['recent_appointments'] = appointments.filter(starts_at__lt=now).order_by('-starts_at')[:8]
            context['upcoming_appointments'] = appointments.filter(starts_at__gte=now, status=Appointment.Status.SCHEDULED).order_by('starts_at')[:5]
            from apps.appointments.session_summary import prepare_session_summaries
            recent = list(context['recent_appointments'])
            upcoming = list(context['upcoming_appointments'])
            sessions = {session.pk: session for session in recent + upcoming + ([consultation] if consultation else [])}
            prepare_session_summaries(sessions.values(), self.request.user)
            context['recent_appointments'] = [sessions[session.pk] for session in recent]
            context['upcoming_appointments'] = [sessions[session.pk] for session in upcoming]
            context['initial_consultation'] = sessions.get(consultation.pk) if consultation else None
            if has_practice_permission(self.request.user, 'appointments', 'edit'):
                context['session_editor_appointments'] = list(sessions.values())
        if has_practice_permission(self.request.user, 'appointments', 'create') or context.get('session_editor_appointments'):
            from apps.appointments.access import manages_sessions
            from apps.practices.models import ExternalIntegration
            context['appointment_clients'] = [client]
            context['appointment_therapists'] = client.practice.therapists.select_related('user')
            if not manages_sessions(self.request.user):
                context['appointment_therapists'] = context['appointment_therapists'].filter(user=self.request.user)
            from apps.appointments.forms import RecurrenceForm
            context['recurrence_form'] = RecurrenceForm(auto_id='appointment-create-%s')
            context['session_kind_choices'] = Appointment.SessionKind.choices
            context['calendar_anchor_date'] = timezone.localdate()
            context['google_calendar_connected'] = ExternalIntegration.objects.filter(practice=client.practice,
                provider=ExternalIntegration.Provider.GOOGLE, status=ExternalIntegration.Status.CONNECTED, calendar_enabled=True).exists()

        if permissions['intake']:
            context['portal_access'] = ClientPortalAccess.objects.filter(client=client, practice=client.practice).first()
        if active_tab == 'billing':
            invoices = list(Invoice.objects.filter(client=client, practice=client.practice).annotate(
                workspace_paid=Sum('payments__amount'),
            ).order_by('-created_at')[:20])
            for invoice in invoices:
                invoice.workspace_balance = max(invoice.amount - (invoice.workspace_paid or Decimal('0.00')), Decimal('0.00'))
            context['invoices'] = invoices
            context['packages'] = ServicePackage.objects.filter(client=client, practice=client.practice).order_by('-created_at')[:8]
        if active_tab == 'documents':
            context['documents'] = ClientDocument.objects.filter(client=client, practice=client.practice).order_by('-created_at')[:20]
        if active_tab == 'clinical':
            context['notes'] = scope_sessions(SessionNote.objects.filter(client=client, practice=client.practice), self.request.user).select_related('therapist__user', 'treatment_plan').order_by('-updated_at')[:8]
            context['treatment_plans'] = TreatmentPlan.objects.filter(client=client, practice=client.practice).prefetch_related('diagnoses').order_by('-updated_at')[:8]
            diagnoses = list(Diagnosis.objects.filter(client=client, practice=client.practice))
            context['diagnoses'] = diagnoses
            if has_practice_permission(self.request.user, 'clinical', 'create'):
                context['diagnosis_create_form'] = DiagnosisForm(practice=client.practice, patient=client, auto_id='diagnosis-create-%s')
            if has_practice_permission(self.request.user, 'clinical', 'edit'):
                context['diagnosis_edit_forms'] = [
                    (diagnosis, DiagnosisForm(instance=diagnosis, practice=client.practice,
                        patient=client, auto_id=f'diagnosis-edit-{diagnosis.pk}-%s'))
                    for diagnosis in diagnoses
                ]
        from .chart_context import add_chart_context
        permissions['appointments_edit'] = has_practice_permission(self.request.user, 'appointments', 'edit')
        add_chart_context(context, self.request, client, permissions)
        return context


class ClientCreateView(LoginRequiredMixin, PracticePermissionMixin, PracticeContextMixin, CreateView):
    permission_resource = 'clients'
    permission_action = 'create'
    model = Client
    form_class = ClientForm
    template_name = 'clients/form.html'
    success_url = reverse_lazy('clients:list')

    def get_success_url(self):
        if self.request.POST.get('open_workspace') == '1':
            return reverse('clients:detail', args=[self.object.pk])
        return super().get_success_url()

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['practice'] = self.get_practice()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'New Client'
        context['form_heading'] = 'Create a client profile'
        context['submit_label'] = 'Create client'
        return context


class ClientUpdateView(LoginRequiredMixin, PracticePermissionMixin, PracticeContextMixin, UpdateView):
    permission_resource = 'clients'
    permission_action = 'edit'
    model = Client
    form_class = ClientForm
    template_name = 'clients/form.html'
    success_url = reverse_lazy('clients:list')

    def get_success_url(self):
        if self.request.POST.get('open_workspace') == '1':
            return reverse('clients:detail', args=[self.object.pk])
        return super().get_success_url()

    def get_queryset(self):
        practice = self.get_practice()
        if not practice:
            return Client.objects.none()

        return Client.objects.filter(practice=practice)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['practice'] = self.get_practice()
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form_title'] = 'Edit Client'
        context['form_heading'] = 'Edit client profile'
        context['submit_label'] = 'Save changes'
        context['show_delete_action'] = True
        return context


class ClientDeleteView(LoginRequiredMixin, PracticePermissionMixin, PracticeContextMixin, DeleteView):
    permission_resource = 'clients'
    permission_action = 'delete'
    model = Client
    success_url = reverse_lazy('clients:list')

    def get_queryset(self):
        practice = self.get_practice()
        if not practice:
            return Client.objects.none()

        return Client.objects.filter(practice=practice)

    def form_valid(self, form):
        try:
            return super().form_valid(form)
        except ProtectedError:
            self.request._audit_denied_reason = 'clinical_record_retained'
            messages.error(self.request, 'This client has clinical records and must be retained. Archive the client instead.')
            return redirect('clients:detail', pk=self.object.pk)
