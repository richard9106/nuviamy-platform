"""Operator-configured, expiring access for an isolated fictional OAuth review tenant."""
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime

REVIEW_USERNAME = 'google-oauth-review'
REVIEW_PRACTICE_SLUG = 'google-oauth-review-demo'


def is_review_identity(user):
    return bool(user.is_authenticated and user.username == REVIEW_USERNAME)


def review_access_valid(user):
    if not is_review_identity(user) or not user.is_active or user.is_staff or user.is_superuser:
        return False
    try:
        expires = parse_datetime(settings.GOOGLE_REVIEW_ACCESS_EXPIRES_AT)
        if not expires or timezone.is_naive(expires) or expires <= timezone.now():
            return False
        profile = user.nuvia_profile
        therapist = user.therapist_profile
        return bool(
            str(user.pk) == settings.GOOGLE_REVIEW_USER_ID
            and str(profile.practice_id) == settings.GOOGLE_REVIEW_PRACTICE_ID
            and profile.role == 'therapist'
            and therapist.practice_id == profile.practice_id
            and profile.practice.public_booking_slug == REVIEW_PRACTICE_SLUG
        )
    except (AttributeError, ValueError):
        return False


def requires_email_verification(user):
    return settings.EMAIL_TWO_STEP_REQUIRED and not review_access_valid(user)
