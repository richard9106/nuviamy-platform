"""Finite weekly plans, generated in the scheduling timezone without DB writes."""
from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.utils import timezone

MAX_SESSIONS = 52


def weekly_starts(starts_at, *, interval=1, weekdays=None, count=None, until=None):
    local_start = timezone.localtime(starts_at)
    days = sorted(set(weekdays if weekdays is not None else [local_start.weekday()]))
    if not days or any(day not in range(7) for day in days):
        raise ValidationError('Choose at least one valid weekday.')
    if local_start.weekday() not in days:
        raise ValidationError('Include the first appointment’s weekday, or change its start date.')
    if not 1 <= interval <= 12:
        raise ValidationError('Repeat intervals must be between 1 and 12 weeks.')
    if count is not None and not 1 <= count <= MAX_SESSIONS:
        raise ValidationError('Choose between 1 and 52 sessions.')
    if count is None and until is None:
        raise ValidationError('Choose a session count or an end date.')
    if until and until < local_start.date():
        raise ValidationError('The end date cannot be before the first appointment.')
    week = local_start.date() - timedelta(days=local_start.weekday())
    result = []
    try:
        while True:
            for weekday in days:
                day = week + timedelta(days=weekday)
                if day < local_start.date():
                    continue
                if until and day > until:
                    return result
                naive = datetime.combine(day, local_start.time().replace(tzinfo=None))
                early = naive.replace(tzinfo=local_start.tzinfo, fold=0)
                late = naive.replace(tzinfo=local_start.tzinfo, fold=1)
                if early.utcoffset() != late.utcoffset():
                    raise ValidationError(f'The session on {day:%b %d, %Y} falls in an ambiguous or missing clock-change hour. Choose another time.')
                result.append(early)
                if len(result) > MAX_SESSIONS:
                    raise ValidationError('This rule creates more than 52 sessions. Use an earlier end date or fewer weekdays.')
                if count and len(result) == count:
                    return result
            week += timedelta(weeks=interval)
    except OverflowError:
        raise ValidationError('The recurrence extends beyond supported calendar dates.')
