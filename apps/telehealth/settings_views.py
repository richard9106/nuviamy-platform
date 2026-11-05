from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404
from django.shortcuts import render,redirect
from django.views import View
from apps.accounts.contract_views import ContractOwnerMixin
from apps.practices.models import Practice,ExternalIntegration
from apps.audit.models import AuditLog
from apps.rate_limit import PostRateLimitMixin
from .activation import VideoActivationForm,activate,accepted,available,base_ready,text
from .access import enabled_for


class VideoSettingsView(ContractOwnerMixin,PostRateLimitMixin,View):
    rate_limit_scope='video_settings'
    rate_limit_count=20
    rate_limit_seconds=900

    def get(self,request):
        return self.show(request)

    def show(self,request,form=None):
        if not available(self.practice.pk):raise Http404
        return render(request,'telehealth/settings.html',{'video_enabled':enabled_for(self.practice.pk),
            'video_acceptance':accepted(self.practice.pk),'video_blocks':[{'heading':block.startswith('#'),'text':block.lstrip('# ')} for block in text().strip().split('\n\n')],'base_ready':base_ready(self.practice.pk),
            'form':form or VideoActivationForm(initial={'representative_name':request.user.get_full_name()})})

    def post(self,request):
        if not available(self.practice.pk):raise Http404
        if request.POST.get('action')=='disable':
            with transaction.atomic():
                Practice.objects.select_for_update().get(pk=self.practice.pk)
                ExternalIntegration.objects.update_or_create(practice=self.practice,provider='chime',defaults={'status':'disconnected'})
                AuditLog.objects.create(practice=self.practice,actor=request.user,action=AuditLog.Action.UPDATE,object_type='telehealth_settings',object_id=str(self.practice.pk),metadata={'event':'video_disabled'})
            messages.success(request,'Video sessions disabled. Active rooms will close automatically.')
            return redirect('telehealth:settings')
        if request.POST.get('action')!='enable':raise Http404
        form=VideoActivationForm(request.POST)
        if form.is_valid():
            try:activate(request.user,self.practice,form.cleaned_data)
            except ValidationError as error:form.add_error(None,error)
            else:
                messages.success(request,'Video sessions are enabled for your practice.')
                return redirect('telehealth:settings')
        return self.show(request,form)
