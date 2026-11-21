from django import forms

from .models import Client


class AdministrativeNoteForm(forms.Form):
    content = forms.CharField(max_length=4000, strip=True, label='Administrative note',
        widget=forms.Textarea(attrs={'rows': 3, 'placeholder': 'Record a call or an administrative update. Clinical notes belong in Clinical.'}))


class ClientFormsShareForm(forms.Form):
    templates = forms.ModelMultipleChoiceField(queryset=None, label='Forms to share', widget=forms.CheckboxSelectMultiple)
    notify = forms.BooleanField(required=False, initial=True, label='Send a generic email notification')
    invite_portal = forms.BooleanField(required=False, label='Create portal access and send an account setup invitation')

    def __init__(self, *args, practice, client, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.portal.models import ClientPortalAccess, IntakePacketTemplate
        self.fields['templates'].queryset = IntakePacketTemplate.objects.filter(practice=practice, active=True).order_by('name')
        self.client = client
        self.access = ClientPortalAccess.objects.filter(client=client, practice=practice).select_related('user').first()

    def clean_templates(self):
        templates = self.cleaned_data['templates']
        if templates.count() > 30:
            raise forms.ValidationError('Share up to 30 forms at a time.')
        return templates

    def clean(self):
        data = super().clean()
        if data.get('invite_portal') and self.access:
            self.add_error('invite_portal', 'Portal access already exists. Manage it separately if it is inactive.')
        if data.get('notify'):
            if self.access:
                if not self.access.is_active or not self.access.user.is_active or not self.access.user.email:
                    self.add_error('notify', 'The portal account must be active and have an email address.')
            elif not data.get('invite_portal'):
                self.add_error('notify', 'Select portal invitation, or assign without an email.')
        if data.get('invite_portal') and not self.client.email:
            self.add_error('invite_portal', 'Add the client email address before inviting them.')
        return data


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'first_name',
            'last_name',
            'profile_photo',
            'email',
            'phone',
            'date_of_birth',
            'status',
            'primary_therapist',
            'billing_type', 'insurance_payer', 'insurance_state', 'insurance_copay',
            'insurance_provider',
            'insurance_member_id',
            'emergency_contact_name',
            'emergency_contact_phone',
            'address_line1',
            'address_line2',
        ]
        widgets = {
            'date_of_birth': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'phone': forms.TextInput(attrs={'type': 'tel'}),
            'emergency_contact_phone': forms.TextInput(attrs={'type': 'tel'}),
        }

    def __init__(self, *args, practice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.practice = practice
        self.instance.practice = practice

        from apps.billing.insurance import available_payers
        from apps.billing.models import InsurancePayer
        from django.db.models import Q
        payers = available_payers(practice)
        if self.instance.pk and self.instance.insurance_payer_id:
            payers = InsurancePayer.objects.filter(Q(pk__in=payers.values('pk')) | Q(pk=self.instance.insurance_payer_id))
        self.fields['insurance_payer'].queryset = payers
        self.fields['billing_type'].required = False
        self.fields['insurance_provider'].label = 'Legacy / reference insurance name'
        self.fields['insurance_copay'].label = 'Expected client share per session (USD)'
        if practice:
            self.fields['primary_therapist'].queryset = practice.therapists.select_related('user')
        else:
            self.fields['primary_therapist'].queryset = self.fields['primary_therapist'].queryset.none()

    def clean(self):
        data = super().clean()
        data['billing_type'] = data.get('billing_type') or 'self_pay'
        payer = data.get('insurance_payer')
        from apps.billing.insurance import available_payers
        if payer and payer.pk != self.instance.insurance_payer_id and not available_payers(self.practice).filter(pk=payer.pk).exists():
            self.add_error('insurance_payer', 'Enable this payer in Insurance settings first.')
        if data['billing_type'] == 'insurance' and not payer:
            self.add_error('insurance_payer', 'Choose an enabled insurance payer.')
        state = (data.get('insurance_state') or '').upper()
        if state and (len(state) != 2 or not state.isascii() or not state.isalpha()):
            self.add_error('insurance_state', 'Use a two-letter US state code.')
        data['insurance_state'] = state
        if payer:
            data['insurance_provider'] = payer.name
        return data

    def save(self, commit=True):
        client = super().save(commit=False)
        client.practice = self.practice
        if commit:
            client.full_clean()
            client.save()
            self.save_m2m()
        return client
