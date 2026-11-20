from copy import deepcopy

from django import forms

from .models import Appointment, CalendarEvent, PracticeAvailabilityOverride, PracticeWorkingHour


class RecurrenceForm(forms.Form):
    recurrence_rule = forms.ChoiceField(required=False, initial='none', label='Repeat', choices=[('none', 'Does not repeat'), ('weekly', 'Weekly')])
    recurrence_interval = forms.IntegerField(required=False, min_value=1, max_value=12, initial=1, label='Every (weeks)')
    recurrence_weekdays = forms.MultipleChoiceField(required=False, label='On these days', choices=[(str(i), day) for i, day in enumerate(('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'))], widget=forms.CheckboxSelectMultiple)
    recurrence_ends = forms.ChoiceField(required=False, initial='count', label='Ends', choices=[('count', 'After a number of sessions'), ('date', 'On a date')])
    repeat_weekly_count = forms.IntegerField(required=False, min_value=1, max_value=52, initial=4, label='Total sessions', help_text='Includes the first appointment. Maximum 52.')
    recurrence_until = forms.DateField(required=False, label='Last date (inclusive)', widget=forms.DateInput(attrs={'type': 'date'}))


RECURRENCE_FIELDS = tuple(RecurrenceForm.base_fields)


class AppointmentForm(forms.ModelForm):
    class Meta:
        model = Appointment
        fields = [
            'client',
            'therapist',
            'starts_at',
            'ends_at',
            'session_kind',
            'appointment_type',
            'status',
            'location',
            'meeting_url',
            'notes',
        ]
        labels = {'session_kind': 'Session', 'appointment_type': 'Format'}
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'ends_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'notes': forms.Textarea(attrs={'rows': 4}),
        }

    def __init__(self, *args, practice=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields.update(deepcopy(RecurrenceForm.base_fields))
        self.fields['session_kind'].required = False
        self.practice = practice
        self.instance.practice = practice
        if self.instance.pk:
            for name in RECURRENCE_FIELDS:
                self.fields.pop(name, None)
        elif self.is_bound:
            rule = self.data.get(self.add_prefix('recurrence_rule'), '')
            for name in RECURRENCE_FIELDS:
                if name == 'recurrence_rule':
                    continue
                inactive = rule == 'none' or (not rule and name != 'repeat_weekly_count')
                if rule == 'weekly':
                    ends = self.data.get(self.add_prefix('recurrence_ends'), 'count') or 'count'
                    inactive = name == ('recurrence_until' if ends == 'count' else 'repeat_weekly_count')
                if inactive:
                    self.fields[name].disabled = True
        self.fields['starts_at'].input_formats = ['%Y-%m-%dT%H:%M']
        self.fields['ends_at'].input_formats = ['%Y-%m-%dT%H:%M']

        if practice:
            self.fields['client'].queryset = practice.clients.all()
            self.fields['therapist'].queryset = practice.therapists.select_related('user')
            if not self.is_bound and not self.instance.pk and not self.initial.get('therapist'):
                candidates = list(self.fields['therapist'].queryset[:2])
                if len(candidates) == 1:
                    self.initial['therapist'] = candidates[0].pk
        else:
            self.fields['client'].queryset = self.fields['client'].queryset.none()
            self.fields['therapist'].queryset = self.fields['therapist'].queryset.none()

        if user:
            from .access import manages_sessions
            if not manages_sessions(user):
                self.fields['therapist'].queryset = self.fields['therapist'].queryset.filter(user=user)
                self.initial['therapist'] = self.fields['therapist'].queryset.values_list('pk', flat=True).first()

    def clean(self):
        cleaned = super().clean()
        self.planned_starts = []
        start = cleaned.get('starts_at')
        if self.instance.pk or not start:
            return cleaned
        from .recurrence import weekly_starts
        rule = cleaned.get('recurrence_rule')
        if rule == 'none':
            self.planned_starts = [start]
            return cleaned
        if rule == 'weekly':
            mode = cleaned.get('recurrence_ends') or 'count'
            count = cleaned.get('repeat_weekly_count') if mode == 'count' else None
            until = cleaned.get('recurrence_until') if mode == 'date' else None
            if mode == 'count' and count is None:
                self.add_error('repeat_weekly_count', 'Enter the total number of sessions.')
                return cleaned
            if mode == 'date' and until is None:
                self.add_error('recurrence_until', 'Choose the last date.')
                return cleaned
            if not cleaned.get('recurrence_weekdays'):
                self.add_error('recurrence_weekdays', 'Choose at least one weekday.')
            if self.errors:
                return cleaned
            self.planned_starts = weekly_starts(start, interval=cleaned.get('recurrence_interval') or 1,
                weekdays=[int(day) for day in cleaned.get('recurrence_weekdays', [])] or None,
                count=count, until=until)
        else:
            # Existing integrations posting only repeat_weekly_count retain their behavior.
            self.planned_starts = weekly_starts(start, count=cleaned.get('repeat_weekly_count') or 1)
        return cleaned

    def clean_session_kind(self):
        return self.cleaned_data.get('session_kind') or self.instance.session_kind or Appointment.SessionKind.STANDARD

    def save(self, commit=True):
        appointment = super().save(commit=False)
        appointment.practice = self.practice
        if commit:
            appointment.full_clean()
            appointment.save()
            self.save_m2m()
        return appointment


class PracticeWorkingHourForm(forms.ModelForm):
    class Meta:
        model = PracticeWorkingHour
        fields = ['weekday', 'starts_at', 'ends_at', 'active']
        widgets = {
            'starts_at': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'ends_at': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }

    def __init__(self, *args, practice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.practice = practice
        self.instance.practice = practice
        self.fields['starts_at'].input_formats = ['%H:%M']
        self.fields['ends_at'].input_formats = ['%H:%M']

    def save(self, commit=True):
        working_hour = super().save(commit=False)
        working_hour.practice = self.practice
        if commit:
            working_hour.full_clean()
            working_hour.save()
            self.save_m2m()
        return working_hour


class CalendarAvailabilityEditForm(forms.ModelForm):
    class Meta:
        model = PracticeAvailabilityOverride
        fields = ['date', 'is_available', 'starts_at', 'ends_at', 'note']
        labels = {'is_available': 'Available during these hours', 'starts_at': 'Start time', 'ends_at': 'End time'}
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'starts_at': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'ends_at': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # An edit changes one existing date, never a whole recurring series.
        self.fields['date'].disabled = True
        for field in ('starts_at', 'ends_at'):
            self.fields[field].input_formats = ['%H:%M']


class PracticeAvailabilityOverrideForm(forms.ModelForm):
    REPEAT_NONE = 'none'
    REPEAT_WEEKLY = 'weekly'
    REPEAT_MONTHLY = 'monthly'
    REPEAT_CHOICES = (
        (REPEAT_NONE, 'Only this date'),
        (REPEAT_WEEKLY, 'Repeat weekly'),
        (REPEAT_MONTHLY, 'Repeat monthly'),
    )

    repeat = forms.ChoiceField(choices=REPEAT_CHOICES, required=False, initial=REPEAT_NONE)
    repeat_count = forms.IntegerField(min_value=1, max_value=52, required=False, initial=1, label='Occurrences')
    end_date = forms.DateField(required=False, widget=forms.DateInput(attrs={'type': 'date'}), label='End date')

    class Meta:
        model = PracticeAvailabilityOverride
        fields = ['date', 'is_available', 'starts_at', 'ends_at', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'starts_at': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'ends_at': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
        }
        labels = {
            'is_available': 'Available during these hours',
            'starts_at': 'Start time',
            'ends_at': 'End time',
        }

    def __init__(self, *args, practice=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.practice = practice
        self.instance.practice = practice
        self.fields['starts_at'].input_formats = ['%H:%M']
        self.fields['ends_at'].input_formats = ['%H:%M']

    def clean(self):
        cleaned_data = super().clean()
        repeat = cleaned_data.get('repeat') or self.REPEAT_NONE
        repeat_count = cleaned_data.get('repeat_count') or 1
        start_date = cleaned_data.get('date')
        end_date = cleaned_data.get('end_date')
        if end_date and start_date and end_date < start_date:
            self.add_error('end_date', 'End date must be on or after the start date.')
        if end_date:
            cleaned_data['repeat'] = self.REPEAT_NONE
            cleaned_data['repeat_count'] = 1
        elif repeat == self.REPEAT_NONE:
            cleaned_data['repeat_count'] = 1
        elif repeat_count < 2:
            self.add_error('repeat_count', 'Use at least 2 occurrences when repeating availability.')
        return cleaned_data

    def save(self, commit=True):
        override = super().save(commit=False)
        override.practice = self.practice
        if commit:
            override.full_clean()
            override.save()
            self.save_m2m()
        return override


class CalendarEventForm(forms.ModelForm):
    class Meta:
        model = CalendarEvent
        fields = ['title', 'therapist', 'starts_at', 'ends_at', 'location']
        widgets = {
            'starts_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
            'ends_at': forms.DateTimeInput(attrs={'type': 'datetime-local'}, format='%Y-%m-%dT%H:%M'),
        }

    def __init__(self, *args, practice=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        from .access import manages_sessions
        self.instance.practice = practice
        self.fields['therapist'].queryset = practice.therapists.select_related('user') if practice else self.fields['therapist'].queryset.none()
        if user and not manages_sessions(user):
            self.fields['therapist'].queryset = self.fields['therapist'].queryset.filter(user=user)
        if self.fields['therapist'].queryset.count() == 1:
            self.initial.setdefault('therapist', self.fields['therapist'].queryset.first().pk)
        for name in ('starts_at', 'ends_at'):
            self.fields[name].input_formats = ['%Y-%m-%dT%H:%M']
