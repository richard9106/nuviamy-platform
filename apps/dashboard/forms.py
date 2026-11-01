from django import forms
from django.contrib.auth import get_user_model

from apps.accounts.models import UserProfile
from .models import Task, SupportTicket


class SupportContactForm(forms.Form):
    name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()
    topic = forms.ChoiceField(choices=SupportTicket.Topic.choices)
    message = forms.CharField(widget=forms.Textarea(attrs={'rows': 6}), max_length=4000)
    website = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_website(self):
        value = self.cleaned_data['website']
        if value:
            raise forms.ValidationError('Unable to send this request.')
        return value


class SupportReplyForm(forms.Form):
    message = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={'rows': 4}))


class FoundingTherapistApplicationForm(SupportContactForm):
    topic = None
    message = None
    name = forms.CharField(max_length=150, label='Your name', widget=forms.TextInput(attrs={'autocomplete': 'name'}))
    practice_name = forms.CharField(max_length=150, label='Practice name', required=False)
    country = forms.CharField(max_length=100, label='Country', widget=forms.TextInput(attrs={'autocomplete': 'country-name'}))
    profession = forms.ChoiceField(choices=[('', 'Choose your role'), ('therapist', 'Therapist'),
        ('psychologist', 'Psychologist'), ('counselor', 'Counselor'), ('owner', 'Practice owner / manager'),
        ('other', 'Other mental health professional')])
    contact_permission = forms.BooleanField(label='Contact me by email about this application. I understand that a place is subject to review and an invitation.')

    def clean(self):
        cleaned = super().clean()
        from apps.practices.models import FoundingTherapistInvitation
        if not FoundingTherapistInvitation.objects.filter(email='', redeemed_at__isnull=True).exists():
            raise forms.ValidationError('All 50 invitations have been allocated. You can still start the standard 30-day trial.')
        cleaned['topic'] = SupportTicket.Topic.EARLY_ACCESS
        cleaned['message'] = '\n'.join([
            'Founding therapist application — campaign: 50 places / six months.',
            f"Practice: {cleaned.get('practice_name', '')}",
            f"Country: {cleaned.get('country', '')}",
            f"Role: {dict(self.fields['profession'].choices).get(cleaned.get('profession'), '')}",
            'Applicant requested email contact about this application; no marketing subscription.',
        ])
        return cleaned


class TaskForm(forms.ModelForm):
    class Meta:
        model = Task
        fields = ('title', 'description', 'due_date', 'priority', 'status', 'assignee')
        widgets = {
            'description': forms.Textarea(attrs={'rows': 4}),
            'due_date': forms.DateInput(attrs={'type': 'date'}),
        }

    def __init__(self, *args, practice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.practice_id = practice.pk if practice else None
        self.fields['assignee'].queryset = get_user_model().objects.filter(
            nuvia_profile__practice=practice,
        ).exclude(nuvia_profile__role=UserProfile.Role.CLIENT).order_by('first_name', 'username')
        self.fields['assignee'].label_from_instance = lambda user: user.get_full_name() or user.username

    def clean_assignee(self):
        assignee = self.cleaned_data['assignee']
        if assignee.nuvia_profile.practice_id != self.practice_id:
            raise forms.ValidationError('Choose a team member from this practice.')
        return assignee
