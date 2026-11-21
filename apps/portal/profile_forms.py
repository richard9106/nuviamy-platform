import uuid
from pathlib import PurePath
from django import forms
from django.utils import timezone
from apps.billing.insurance import available_payers
from apps.documents.uploads import validate_document_upload


class PortalProfileForm(forms.Form):
    submission_key = forms.UUIDField(initial=uuid.uuid4, widget=forms.HiddenInput)
    first_name = forms.CharField(max_length=80, label='Legal first name')
    last_name = forms.CharField(max_length=80, label='Legal last name')
    middle_name = forms.CharField(max_length=80, required=False)
    preferred_name = forms.CharField(max_length=80, required=False, label='What name do you go by?')
    is_minor = forms.BooleanField(required=False, label='Client is a minor')
    email = forms.EmailField(required=False, label='Contact email')
    phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'type':'tel'}))
    phone_type = forms.ChoiceField(choices=[('mobile','Mobile'),('home','Home'),('work','Work')])
    email_reminders_allowed = forms.BooleanField(required=False, label='Allow appointment reminders by email when offered by my practice')
    address_line1 = forms.CharField(max_length=140, required=False, label='Street address')
    address_line2 = forms.CharField(max_length=140, required=False, label='Apartment or suite')
    city = forms.CharField(max_length=100, required=False)
    state = forms.CharField(max_length=100, required=False, label='State / region')
    postal_code = forms.CharField(max_length=20, required=False)
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(format='%Y-%m-%d', attrs={'type':'date'}))
    sex = forms.ChoiceField(required=False, choices=[('','Prefer not to say'),('female','Female'),('male','Male'),('intersex','Intersex'),('other','Another description')])
    relationship_status = forms.ChoiceField(required=False, choices=[('','No answer'),('single','Single'),('partnered','Partnered'),('married','Married'),('separated','Separated'),('divorced','Divorced'),('widowed','Widowed')])
    employment_status = forms.ChoiceField(required=False, choices=[('','No answer'),('employed','Employed'),('self_employed','Self-employed'),('student','Student'),('not_employed','Not employed'),('retired','Retired'),('other','Other')])
    emergency_contact_name = forms.CharField(max_length=120, required=False)
    emergency_contact_relationship = forms.CharField(max_length=80, required=False, label='Relationship to emergency contact')
    emergency_contact_phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={'type':'tel'}))
    insurance_payer = forms.ModelChoiceField(queryset=None, required=False, label='Insurance company accepted by this practice')
    insurance_company = forms.CharField(max_length=140, required=False, label='Other insurance company / reference name')
    insurance_member_id = forms.CharField(max_length=80, required=False, label='Member ID')
    insurance_group_id = forms.CharField(max_length=80, required=False, label='Group ID')
    insurance_plan_id = forms.CharField(max_length=80, required=False, label='Plan ID')
    insured_relationship = forms.ChoiceField(choices=[('self','Client (self)'),('spouse',"Client’s spouse"),('parent',"Client’s parent"),('other','Other')], required=False)
    insurance_front = forms.FileField(required=False, label='Front of insurance card', widget=forms.ClearableFileInput(attrs={'accept':'.jpg,.jpeg,.png,.pdf'}))
    insurance_back = forms.FileField(required=False, label='Back of insurance card', widget=forms.ClearableFileInput(attrs={'accept':'.jpg,.jpeg,.png,.pdf'}))
    confirm = forms.BooleanField(label='I reviewed these details and want to share them with my practice.')

    def __init__(self, *args, portal_access, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['insurance_payer'].queryset = available_payers(portal_access.practice)
        client = portal_access.client
        latest = client.profile_submissions.filter(practice=portal_access.practice).first()
        proposed = latest.submitted_details if latest else {}
        for name in self.fields:
            if name in proposed and (latest.status == 'pending' or not hasattr(client, name)):
                self.initial[name] = proposed[name]
            elif hasattr(client, name):
                self.initial[name] = getattr(client, name)
        self.initial['insurance_payer'] = proposed.get('insurance_payer', client.insurance_payer_id) if latest and latest.status == 'pending' else client.insurance_payer_id
        self.initial['email_reminders_allowed'] = client.email_reminders_allowed
        self.initial['confirm'] = False

    def clean_date_of_birth(self):
        value = self.cleaned_data['date_of_birth']
        if value and value > timezone.localdate():
            raise forms.ValidationError('Date of birth cannot be in the future.')
        return value

    def clean(self):
        data = super().clean()
        for name in ('insurance_front','insurance_back'):
            upload = data.get(name)
            if upload:
                try:
                    if PurePath(upload.name).suffix.lower() not in {'.png','.jpg','.jpeg','.pdf'}:
                        raise forms.ValidationError('Use a PNG, JPEG or PDF file up to 10 MB.')
                    validate_document_upload(upload)
                except forms.ValidationError as error:
                    self.add_error(name, error)
        return data

    def serializable_details(self):
        details = {key: value for key,value in self.cleaned_data.items() if key not in ('insurance_front','insurance_back','confirm','submission_key')}
        if details.get('insurance_payer'):
            details['insurance_payer_name'] = details['insurance_payer'].name
            details['insurance_payer'] = details['insurance_payer'].pk
        if details.get('date_of_birth'):
            details['date_of_birth'] = details['date_of_birth'].isoformat()
        return details
