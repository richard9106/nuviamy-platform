import json
from datetime import date
from pathlib import PurePath

from django.contrib import messages
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.generic import FormView

from apps.audit.models import AuditLog
from apps.audit.utils import log_audit_event
from apps.clients.models import Client
from apps.clients.workspace import ClientChartActionView
from apps.documents.models import ClientDocument
from .models import PortalProfileSubmission
from .profile_forms import PortalProfileForm
from .views import ClientPortalAccessMixin


class PortalProfileView(ClientPortalAccessMixin, FormView):
    template_name = 'portal/profile_form.html'
    form_class = PortalProfileForm

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'portal_access': self.get_portal_access()}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['latest_submission'] = PortalProfileSubmission.objects.filter(
            practice=context['portal_practice'],client=context['portal_client']).first()
        return context

    def form_valid(self, form):
        access = self.get_portal_access()
        created_files = []
        try:
            with transaction.atomic():
                client = Client.objects.select_for_update().get(pk=access.client_id, practice=access.practice)
                if PortalProfileSubmission.objects.filter(practice=access.practice,client=client,
                    submission_key=form.cleaned_data['submission_key']).exists():
                    messages.info(self.request,'This information was already submitted; no duplicate files were saved.')
                    return redirect('portal:profile')
                documents = []
                for name, side in [('insurance_front','Front'),('insurance_back','Back')]:
                    upload = form.cleaned_data.get(name)
                    if upload:
                        document = ClientDocument(practice=access.practice, client=client, uploaded_by=self.request.user,
                            title=side + ' of insurance card', document_type='insurance', visible_to_client=True,
                            original_filename=PurePath(upload.name).name[:255], file_size=upload.size, file=upload)
                        document.full_clean()
                        try:
                            document.save()
                        finally:
                            if document.file._committed:
                                created_files.append((document.file.storage, document.file.name))
                        documents.append(document.pk)
                        log_audit_event(self.request, AuditLog.Action.CREATE, 'documents.ClientDocument', document.pk,
                            practice=access.practice, metadata={'client_id': client.pk, 'source':'portal_profile'})
                submission = PortalProfileSubmission.objects.create(practice=access.practice, client=client,
                    submitted_by=self.request.user, details=json.dumps(form.serializable_details()), document_ids=documents,
                    submission_key=form.cleaned_data['submission_key'])
                client.email_reminders_allowed = form.cleaned_data['email_reminders_allowed']
                client.save(update_fields=['email_reminders_allowed'])
                log_audit_event(self.request, AuditLog.Action.CREATE, 'portal.PortalProfileSubmission', submission.pk,
                    practice=access.practice, metadata={'client_id': client.pk, 'document_count':len(documents),
                    'email_reminders_allowed':client.email_reminders_allowed})
        except Exception:
            for storage, name in created_files:
                try:
                    storage.delete(name)
                except Exception:
                    pass
            raise
        messages.success(self.request, 'Your information was sent for practice review. Your reminder preference is saved.')
        return redirect('portal:profile')


class ProfileSubmissionReviewView(ClientChartActionView):
    action = 'edit'

    def get_submission(self, submission_id):
        return get_object_or_404(PortalProfileSubmission, pk=submission_id,
            practice=self.practice, client=self.client_record)

    def get(self, request, pk, submission_id):
        submission = self.get_submission(submission_id)
        form_fields = PortalProfileForm.base_fields
        details = submission.submitted_details
        rows = []
        for name,value in details.items():
            field = form_fields.get(name)
            if not field:
                continue
            if name == 'insurance_payer':
                value = details.get('insurance_payer_name') or 'Not selected'
            if hasattr(field,'choices') and name != 'insurance_payer':
                value = dict(field.choices).get(value, value)
            rows.append((field.label or name.replace('_',' ').capitalize(), value))
        return render(request, 'clients/profile_submission.html', {'client':self.client_record,
            'submission':submission, 'detail_rows':rows,
            'documents':ClientDocument.objects.filter(practice=self.practice, client=self.client_record, pk__in=submission.document_ids)})

    def post(self, request, pk, submission_id):
        request._workspace_drawer_result = 'retry'
        with transaction.atomic():
            client = Client.objects.select_for_update().get(pk=pk, practice=self.practice)
            submission = PortalProfileSubmission.objects.select_for_update().get(pk=self.get_submission(submission_id).pk,
                practice=self.practice,client=client)
            if submission.status != 'pending':
                request._workspace_drawer_result = 'complete'
                messages.info(request,'This submission has already been reviewed.')
                return redirect('clients:detail', pk=pk)
            if request.POST.get('confirm') != 'on' or request.POST.get('action') not in ('apply','reviewed'):
                messages.error(request,'Confirm your review before continuing.')
                return redirect('clients:profile_submission',pk=pk,submission_id=submission_id)
            details = submission.submitted_details
            if request.POST['action'] == 'apply':
                for name in ('first_name','last_name','email','phone','address_line1','address_line2','emergency_contact_name','emergency_contact_phone','insurance_member_id'):
                    setattr(client,name,details.get(name,'') or '')
                client.date_of_birth = date.fromisoformat(details['date_of_birth']) if details.get('date_of_birth') else None
                if details.get('insurance_payer'):
                    from apps.billing.insurance import available_payers
                    payer = available_payers(self.practice).filter(pk=details['insurance_payer']).first()
                    if not payer:
                        messages.error(request,'That insurance payer is no longer available. Review Insurance settings first.')
                        return redirect('clients:profile_submission',pk=pk,submission_id=submission_id)
                    client.insurance_payer = payer
                    client.insurance_provider = payer.name
                    client.billing_type = 'insurance'
                # Never modify account login email, roles, copay or invoice allocations.
                client.full_clean()
                client.save()
                submission.status = 'applied'
            else:
                submission.status = 'reviewed'
            submission.reviewed_by = request.user
            submission.reviewed_at = timezone.now()
            submission.save(update_fields=['status','reviewed_by','reviewed_at'])
            log_audit_event(request,AuditLog.Action.UPDATE,'portal.PortalProfileSubmission',submission.pk,
                practice=self.practice,metadata={'client_id':pk,'status':submission.status})
        messages.success(request,'Client information review recorded. Existing invoices and login credentials are unchanged.')
        request._workspace_drawer_result = 'complete'
        return redirect('clients:detail',pk=pk)
