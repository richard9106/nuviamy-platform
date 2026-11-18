"""Platform operations using business records and existing account workflows."""
import uuid
from datetime import timedelta

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q, Subquery
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from django.views.generic import DetailView, FormView, ListView, TemplateView, View

from apps.accounts.invitations import send_account_access_email
from apps.accounts.models import AccountSecurity, ClinicalContractSignature, StandardAgreementAcceptance, UserProfile
from apps.accounts.standard_agreements import AGREEMENT_VERSION
from apps.appointments.models import SessionEmailNotification
from apps.appointments.notifications import deliver_session_email
from apps.audit.models import AuditLog
from apps.audit.utils import log_audit_event
from apps.billing.access import subscription_access
from apps.billing.models import PracticeSubscription
from apps.practices.founding_offer import issue_founding_offer
from apps.practices.models import FoundingTherapistInvitation, Practice
from apps.rate_limit import PostRateLimitMixin
from .models import SupportTicket
from .support_views import SupportOperatorMixin


INTERNAL_ROLES = (UserProfile.Role.OWNER, UserProfile.Role.ADMIN, UserProfile.Role.THERAPIST)


@method_decorator(never_cache, name='dispatch')
class PlatformOperatorMixin(SupportOperatorMixin, PostRateLimitMixin):
    rate_limit_scope = 'platform-operations'
    rate_limit_count = 30
    rate_limit_seconds = 3600

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['search'] = self.request.GET.get('q', '').strip()[:150]
        context['now'] = timezone.now()
        return context


def internal_accounts():
    return (get_user_model().objects.filter(
        Q(nuvia_profile__role__in=INTERNAL_ROLES) | Q(is_staff=True) | Q(is_superuser=True))
        .filter(client_portal_access__isnull=True))


def practice_directory(search=''):
    practices = Practice.objects.select_related('subscription').annotate(
        member_count=Count('user_profiles', filter=Q(user_profiles__role__in=INTERNAL_ROLES), distinct=True))
    if search:
        practices = practices.filter(Q(name__icontains=search) | Q(email__icontains=search)
            | Q(user_profiles__role='owner', user_profiles__user__email__icontains=search)).distinct()
    return practices.order_by('-created_at', '-pk')


class PlatformOverviewView(PlatformOperatorMixin, TemplateView):
    template_name = 'platform/overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['metrics'] = {
            'practices': Practice.objects.count(),
            'users': internal_accounts().count(),
            'trials': Practice.objects.filter(subscription_required=True, free_access_kind='trial',
                free_trial_ends_at__gt=timezone.now()).exclude(subscription__stripe_subscription_id__gt='').count(),
            'paid': PracticeSubscription.objects.filter(status='active').count(),
            'support': SupportTicket.objects.filter(status='open').count(),
            'offers': FoundingTherapistInvitation.objects.filter(redeemed_at__isnull=False).count(),
        }
        context['recent_practices'] = practice_directory()[:5]
        return context


class PlatformPracticesView(PlatformOperatorMixin, ListView):
    template_name = 'platform/practices.html'
    context_object_name = 'practices'
    paginate_by = 20

    def get_queryset(self):
        return practice_directory(self.request.GET.get('q', '').strip()[:150])


class PlatformPracticeDetailView(PlatformOperatorMixin, DetailView):
    template_name = 'platform/practice_detail.html'
    context_object_name = 'practice'

    def get_queryset(self):
        return practice_directory()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['members'] = internal_accounts().filter(nuvia_profile__practice=self.object).select_related('nuvia_profile')
        context['access'] = subscription_access(self.object)
        context['acceptances'] = self.object.standard_agreements.only('version', 'created_at').order_by('-created_at', '-pk')
        context['support_count'] = SupportTicket.objects.filter(practice=self.object, status='open').count()
        return context


class PlatformUsersView(PlatformOperatorMixin, ListView):
    template_name = 'platform/users.html'
    context_object_name = 'users'
    paginate_by = 20

    def get_queryset(self):
        accounts = internal_accounts().select_related('nuvia_profile__practice').defer('password').annotate(
            mfa_confirmed=Subquery(AccountSecurity.objects.filter(user=OuterRef('pk')).values('confirmed')[:1]))
        search = self.request.GET.get('q', '').strip()[:150]
        if search:
            accounts = accounts.filter(Q(email__icontains=search) | Q(username__icontains=search)
                | Q(first_name__icontains=search) | Q(last_name__icontains=search))
        return accounts.order_by('-date_joined', '-pk')


class PlatformUserActionView(PlatformOperatorMixin, View):
    @transaction.atomic
    def post(self, request, pk):
        user = get_object_or_404(internal_accounts().select_for_update(of=('self',)), pk=pk)
        if user.is_staff or user.is_superuser or user.pk == request.user.pk:
            messages.error(request, 'Manage privileged account security from its own security settings.')
            return redirect('staff_users')
        action = request.POST.get('action')
        if action == 'resend':
            try:
                sent = send_account_access_email(request, user)
            except Exception:
                # Provider exceptions can include reset links and addresses.
                sent = False
            event = 'platform_access_email_sent' if sent else 'platform_access_email_failed'
            if sent:
                messages.success(request, 'Account access email sent.')
            else:
                messages.error(request, 'The access email could not be sent. Check the account status and email delivery.')
        elif action == 'revoke':
            state, _ = AccountSecurity.objects.get_or_create(user=user)
            state = AccountSecurity.objects.select_for_update().get(pk=state.pk)
            state.session_version = uuid.uuid4()
            state.save(update_fields=['session_version'])
            event = 'platform_sessions_revoked'
            messages.success(request, 'Existing sessions revoked. The user can sign in again.')
        else:
            messages.error(request, 'Choose an available account action.')
            return redirect('staff_users')
        log_audit_event(request, AuditLog.Action.UPDATE, 'auth.User', user.pk,
            platform=True, metadata={'event': event})
        return redirect('staff_users')


class FoundingOfferIssueForm(forms.Form):
    email = forms.EmailField(label='Applicant email', max_length=254)
    rotate = forms.BooleanField(required=False, label='Replace an unused code already issued to this email')


class PlatformOffersView(PlatformOperatorMixin, FormView):
    template_name = 'platform/offers.html'
    form_class = FoundingOfferIssueForm

    def get_initial(self):
        initial = super().get_initial()
        application = self.request.GET.get('application')
        if application:
            try:
                application_id = uuid.UUID(application)
            except ValueError:
                return initial
            ticket = SupportTicket.objects.filter(pk=application_id, topic='early_access').first()
            if ticket:
                initial['email'] = ticket.contact_email
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['invitations'] = FoundingTherapistInvitation.objects.exclude(email='').select_related('practice').defer('token_hash').order_by('slot')
        context['available'] = FoundingTherapistInvitation.objects.filter(email='', redeemed_at__isnull=True).count()
        context['applications'] = SupportTicket.objects.filter(topic='early_access', status='open').order_by('-created_at')[:20]
        return context

    def form_valid(self, form):
        try:
            with transaction.atomic():
                issued = issue_founding_offer(form.cleaned_data['email'], rotate=form.cleaned_data['rotate'])
                invitation_pk = FoundingTherapistInvitation.objects.values_list('pk', flat=True).get(slot=issued['slot'])
                log_audit_event(self.request, AuditLog.Action.UPDATE, 'practices.FoundingTherapistInvitation',
                    invitation_pk, platform=True, metadata={'event': 'platform_offer_issued',
                        'rotated': form.cleaned_data['rotate']})
        except ValidationError as error:
            form.add_error(None, error)
            return self.form_invalid(form)
        # Display once. Raw codes are never stored in sessions, messages or audit logs.
        return self.render_to_response(self.get_context_data(form=self.form_class(), issued=issued))


class PlatformSubscriptionsView(PlatformOperatorMixin, ListView):
    template_name = 'platform/subscriptions.html'
    context_object_name = 'practices'
    paginate_by = 20

    def get_queryset(self):
        query = practice_directory(self.request.GET.get('q', '').strip()[:150])
        status = self.request.GET.get('status', '')
        if status in PracticeSubscription.Status.values:
            query = query.filter(subscription__status=status)
        return query

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['statuses'] = PracticeSubscription.Status.choices
        context['selected_status'] = self.request.GET.get('status', '')
        for practice in context['practices']:
            practice.access_state = subscription_access(practice)
        return context


class PlatformNotificationsView(PlatformOperatorMixin, ListView):
    template_name = 'platform/notifications.html'
    context_object_name = 'notifications'
    paginate_by = 20

    def get_queryset(self):
        query = SessionEmailNotification.objects.select_related('practice', 'recipient').defer('recipient__password')
        state = self.request.GET.get('state', '')
        if state in SessionEmailNotification.State.values:
            query = query.filter(state=state)
        return query.order_by('-created_at', '-pk')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['states'] = SessionEmailNotification.State.choices
        context['selected_state'] = self.request.GET.get('state', '')
        context['retry_cutoff'] = timezone.now() - timedelta(hours=24)
        return context

    @transaction.atomic
    def post(self, request):
        try:
            target = forms.IntegerField(min_value=1, max_value=2**63 - 1).clean(request.POST.get('notification'))
        except ValidationError:
            messages.error(request, 'Choose a valid notification.')
            return redirect('staff_notifications')
        notification = get_object_or_404(SessionEmailNotification.objects.select_for_update(), pk=target)
        if (request.POST.get('action') != 'retry' or notification.state != 'failed'
                or notification.created_at <= timezone.now() - timedelta(hours=24)):
            messages.error(request, 'Only recent exhausted alerts can be retried.')
        else:
            notification.state = 'pending'
            notification.attempts = 0
            notification.next_attempt_at = timezone.now()
            notification.save(update_fields=['state', 'attempts', 'next_attempt_at'])
            log_audit_event(request, AuditLog.Action.UPDATE, 'appointments.SessionEmailNotification',
                notification.pk, practice=notification.practice, metadata={'event': 'platform_notification_retry'})
            transaction.on_commit(lambda: deliver_session_email(notification.pk), robust=True)
            messages.success(request, 'Retry requested. Current notification preferences and eligibility will be checked.')
        return redirect('staff_notifications')


class PlatformContractsView(PlatformOperatorMixin, ListView):
    template_name = 'platform/contracts.html'
    context_object_name = 'practices'
    paginate_by = 20

    def get_queryset(self):
        agreements = StandardAgreementAcceptance.objects.filter(practice=OuterRef('pk'))
        return practice_directory(self.request.GET.get('q', '').strip()[:150]).annotate(
            current_agreement=Exists(agreements.filter(version=AGREEMENT_VERSION)),
            accepted_version=Subquery(agreements.exclude(version__startswith='telehealth-')
                .order_by('-created_at', '-pk').values('version')[:1]),
            custom_signed=Exists(ClinicalContractSignature.objects.filter(bundle__request__practice=OuterRef('pk'))))

    def get_context_data(self, **kwargs):
        return super().get_context_data(agreement_version=AGREEMENT_VERSION, **kwargs)


class PlatformActivityView(PlatformOperatorMixin, ListView):
    template_name = 'platform/activity.html'
    context_object_name = 'events'
    paginate_by = 30

    def get_queryset(self):
        query = AuditLog.objects.only('created_at', 'action', 'object_type', 'object_id',
            'actor_username_snapshot', 'practice__name').select_related('practice')
        action = self.request.GET.get('action', '')
        if action in AuditLog.Action.values:
            query = query.filter(action=action)
        return query.order_by('-created_at', '-pk')

    def get_context_data(self, **kwargs):
        return super().get_context_data(actions=AuditLog.Action.choices,
            selected_action=self.request.GET.get('action', ''), **kwargs)
