"""Client chart actions with explicit preview and tenant-scoped writes."""
import hashlib
import json
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views import View

from apps.accounts.access import get_practice_for_user, has_practice_permission, is_client_user
from apps.accounts.invitations import send_account_access_email
from apps.audit.models import AuditLog
from apps.audit.utils import log_audit_event
from apps.portal.forms import ClientPortalAccessForm, suggest_portal_username
from apps.portal.models import ClientIntakeAssignment
from .forms import AdministrativeNoteForm, ClientFormsShareForm
from .models import Client, ClientAdministrativeNote, ClientFormDelivery


def templates_digest(templates):
    contents = [{'id': template.pk, 'name': template.name, 'description': template.description,
                 'questions': template.questions, 'requires_signature': template.requires_signature, 'measure_code': template.measure_code}
                for template in sorted(templates, key=lambda item: item.pk)]
    return hashlib.sha256(json.dumps(contents, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class ClientChartActionView(LoginRequiredMixin, View):
    action = 'view'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            if is_client_user(request.user) or not has_practice_permission(request.user, 'clients', self.action):
                raise PermissionDenied
            self.practice = get_practice_for_user(request.user)
            self.client_record = get_object_or_404(Client, pk=kwargs['pk'], practice=self.practice)
        return super().dispatch(request, *args, **kwargs)


class AdministrativeNoteCreateView(ClientChartActionView):
    action = 'edit'

    def post(self, request, pk):
        form = AdministrativeNoteForm(request.POST)
        if not form.is_valid():
            messages.error(request, 'Enter an administrative note of up to 4,000 characters.')
            from .views import ClientDetailView
            # Keep the entered note in the rendered form rather than losing it on redirect.
            view = ClientDetailView()
            view.setup(request, pk=pk)
            view.object = view.get_object()
            context = view.get_context_data(object=view.object)
            context['administrative_note_form'] = form
            return view.render_to_response(context, status=400)
        with transaction.atomic():
            note = ClientAdministrativeNote(practice=self.practice, client=self.client_record,
                                           author=request.user, content=form.cleaned_data['content'])
            note.full_clean()
            note.save()
            log_audit_event(request, AuditLog.Action.CREATE, 'clients.ClientAdministrativeNote', note.pk,
                            practice=self.practice, metadata={'client_id': pk})
        messages.success(request, 'Administrative note added. It is visible only to authorized practice staff.')
        return redirect(reverse('clients:detail', args=[pk]) + '#client-activity')


class ClientFormsShareView(ClientChartActionView):
    salt = 'clients.form-share.v1'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not has_practice_permission(request.user, 'intake', 'create'):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def page(self, request, form, **extra):
        return render(request, 'clients/share_forms.html', {'client': self.client_record, 'form': form,
            'portal_access': form.access, **extra})

    def get(self, request, pk):
        return self.page(request, ClientFormsShareForm(practice=self.practice, client=self.client_record))

    def post(self, request, pk):
        if request.POST.get('action') == 'edit':
            try:
                data = signing.loads(request.POST.get('share_token', ''), salt=self.salt, max_age=600)
                if data['client'] != pk or data['actor'] != request.user.pk:
                    raise signing.BadSignature
            except (signing.BadSignature, KeyError, TypeError):
                messages.error(request, 'The review expired. Select the forms again.')
                return redirect('clients:share_forms', pk=pk)
            form = ClientFormsShareForm(data, practice=self.practice, client=self.client_record)
            return self.page(request, form)
        if request.POST.get('action') != 'send':
            form = ClientFormsShareForm(request.POST, practice=self.practice, client=self.client_record)
            if not form.is_valid():
                return self.page(request, form)
            target = form.access.user.email if form.access else self.client_record.email
            token = signing.dumps({'client': pk, 'actor': request.user.pk,
                'templates': list(form.cleaned_data['templates'].values_list('pk', flat=True)),
                'notify': form.cleaned_data['notify'], 'invite_portal': form.cleaned_data['invite_portal'],
                'email': target, 'templates_digest': templates_digest(form.cleaned_data['templates']),
                'nonce': uuid.uuid4().hex}, salt=self.salt)
            return self.page(request, form, review=True, share_token=token, recipient=target,
                             selected_templates=form.cleaned_data['templates'])
        try:
            token = request.POST.get('share_token', '')
            data = signing.loads(token, salt=self.salt, max_age=600)
            if data['client'] != pk or data['actor'] != request.user.pk or request.POST.get('confirm') != 'on':
                raise signing.BadSignature
        except (signing.BadSignature, KeyError, TypeError):
            messages.error(request, 'The review expired or was changed. Select and review the forms again.')
            return redirect('clients:share_forms', pk=pk)
        with transaction.atomic():
            self.client_record = Client.objects.select_for_update().get(pk=pk, practice=self.practice)
            digest = hashlib.sha256(token.encode()).hexdigest()
            if ClientFormDelivery.objects.filter(token_digest=digest, practice=self.practice, client=self.client_record).exists():
                messages.info(request, 'This request has already been processed; no duplicate forms or emails were sent.')
                return redirect(reverse('clients:detail', args=[pk]) + '?tab=forms')
            form = ClientFormsShareForm(data, practice=self.practice, client=self.client_record)
            if not form.is_valid():
                return self.page(request, form)
            selected_templates = list(form.cleaned_data['templates'].select_for_update().order_by('pk'))
            if templates_digest(selected_templates) != data.get('templates_digest'):
                form.add_error(None, 'The selected forms changed. Review them again before sending.')
                return self.page(request, form)
            target = form.access.user.email if form.access else self.client_record.email
            if target != data['email']:
                form.add_error(None, 'The recipient changed. Review the forms again before sending.')
                return self.page(request, form)
            access = form.access
            if data['invite_portal']:
                portal_form = ClientPortalAccessForm({'client': pk, 'username': suggest_portal_username(self.client_record),
                    'email': self.client_record.email, 'is_active': True}, practice=self.practice)
                if not portal_form.is_valid():
                    form.add_error(None, 'Portal access could not be created. Review this client’s portal settings and email address.')
                    return self.page(request, form)
                try:
                    access = portal_form.save()
                except ValidationError:
                    form.add_error(None, 'Portal access could not be created. Review the client details.')
                    return self.page(request, form)
                log_audit_event(request, AuditLog.Action.CREATE, 'portal.ClientPortalAccess', access.pk,
                    practice=self.practice, metadata={'client_id': pk, 'portal_user_id': access.user_id})
            delivery = ClientFormDelivery.objects.create(practice=self.practice, client=self.client_record,
                token_digest=digest, delivery_status='pending' if data['notify'] or data['invite_portal'] else 'not_requested')
            log_audit_event(request, AuditLog.Action.CREATE, 'clients.ClientFormDelivery', delivery.pk,
                practice=self.practice, metadata={'client_id': pk,
                    'template_ids': list(form.cleaned_data['templates'].values_list('pk', flat=True)),
                    'email_requested': bool(data['notify'] or data['invite_portal'])})
            for template in selected_templates:
                if not ClientIntakeAssignment.objects.filter(practice=self.practice, client=self.client_record,
                    template=template, status=ClientIntakeAssignment.Status.ASSIGNED).exists():
                    assignment = ClientIntakeAssignment.objects.create(practice=self.practice, client=self.client_record,
                                                                       template=template, assigned_by=request.user)
                    log_audit_event(request, AuditLog.Action.CREATE, 'portal.ClientIntakeAssignment', assignment.pk,
                        practice=self.practice, metadata={'client_id': pk, 'template_id': template.pk, 'delivery_id': delivery.pk})
            if data['notify'] or data['invite_portal']:
                def deliver():
                    try:
                        if not access.user.has_usable_password():
                            sent = send_account_access_email(request, access.user)
                        else:
                            sent = send_mail('NuviaMy: forms ready in your portal',
                                'Hello,\n\nYour practice has shared forms in your secure portal. Sign in to review them:\n'
                                + request.build_absolute_uri(reverse('portal:dashboard'))
                                + '\n\nPlease do not reply with health information.',
                                settings.DEFAULT_FROM_EMAIL, [target], fail_silently=False) == 1
                    except Exception:
                        sent = False
                    ClientFormDelivery.objects.filter(pk=delivery.pk, practice=self.practice,
                        client=self.client_record).update(delivery_status='sent' if sent else 'failed')
                transaction.on_commit(deliver, robust=True)
        messages.success(request, 'Forms assigned. Existing incomplete copies were kept. Check email delivery below.')
        return redirect(reverse('clients:detail', args=[pk]) + '?tab=forms')
