"""Practice-local standard measure library; no automatic emails or diagnoses."""
from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import redirect, render
from django.views import View

from apps.accounts.access import PracticePermissionMixin, get_practice_for_user, has_practice_permission
from apps.audit.models import AuditLog
from apps.audit.utils import log_audit_event
from .measures import ATTRIBUTION, DEFINITIONS, MEASURE_CHOICES, questions_for
from .models import IntakePacketTemplate


class AddMeasureForm(forms.Form):
    measure = forms.ChoiceField(label='Standard measure', choices=MEASURE_CHOICES)
    acknowledge = forms.BooleanField(label='I will choose an appropriate adult client and review responses using my practice’s follow-up process.')


class AddMeasureView(PracticePermissionMixin, View):
    permission_resource = 'intake'
    permission_action = 'create'

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and not has_practice_permission(request.user, 'clinical', 'view'):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get(self, request):
        return render(request, 'intake/add_measure.html', {'form': AddMeasureForm(), 'definitions': DEFINITIONS.values()})

    def post(self, request):
        form = AddMeasureForm(request.POST)
        if not form.is_valid():
            return render(request, 'intake/add_measure.html', {'form': form, 'definitions': DEFINITIONS.values()})
        practice = get_practice_for_user(request.user)
        code = form.cleaned_data['measure']
        definition = DEFINITIONS[code]
        with transaction.atomic():
            # Serialize library creation, including races with another request.
            type(practice).objects.select_for_update().get(pk=practice.pk)
            template = IntakePacketTemplate.objects.filter(practice=practice, measure_code=code).first()
            if not template:
                name = f"{definition['name']} · Standard measure (English)"
                suffix = 2
                base = name
                while IntakePacketTemplate.objects.filter(practice=practice, name=name).exists():
                    name = f'{base} {suffix}'
                    suffix += 1
                template = IntakePacketTemplate(practice=practice, name=name, measure_code=code,
                    description=ATTRIBUTION, questions=questions_for(code))
                template.full_clean()
                template.save()
                log_audit_event(request, AuditLog.Action.CREATE, 'portal.IntakePacketTemplate', template.pk,
                                practice=practice, metadata={'measure_code': code})
        messages.success(request, 'Standard measure is in your library. Assign it or use Share forms from the client record.')
        return redirect('intake:list')
