"""Personal, single-use six-calendar-month access; never creates Stripe charges."""
import calendar
import hashlib
import re
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from django.urls import reverse

from .models import FoundingTherapistInvitation, Practice


def normalize_code(code):
    return re.sub(r'[\s-]', '', code).upper()


def six_months_after(start):
    month_index = start.year * 12 + start.month - 1 + 6
    year, month = divmod(month_index, 12)
    month += 1
    return start.replace(year=year, month=month, day=min(start.day, calendar.monthrange(year, month)[1]))


def offer_for(code, email=None, *, lock=False):
    query = FoundingTherapistInvitation.objects
    if lock:
        query = query.select_for_update()
    normalized = normalize_code(code)
    if not re.fullmatch(r'NUVIA[A-F0-9]{24}', normalized):
        raise ValidationError('This offer code is invalid, expired or already used.')
    invitation = query.filter(token_hash=hashlib.sha256(normalized.encode()).hexdigest()).first()
    if not invitation or invitation.redeemed_at or invitation.expires_at <= timezone.now():
        raise ValidationError('This offer code is invalid, expired or already used.')
    if email and invitation.email.casefold() != email.strip().casefold():
        raise ValidationError('Use the email address this offer code was issued to.')
    return invitation


def redeem_for_practice(invitation, practice, start):
    # Caller holds the invitation lock inside its enclosing account transaction.
    practice.free_access_kind = 'early_access'
    practice.free_trial_started_at = start
    practice.free_trial_ends_at = six_months_after(start)
    practice.save(update_fields=['free_access_kind','free_trial_started_at','free_trial_ends_at'])
    invitation.practice = practice
    invitation.redeemed_at = start
    invitation.save(update_fields=['practice','redeemed_at'])


@transaction.atomic
def redeem_existing_offer(user, code):
    from apps.accounts.models import UserProfile
    from apps.billing.models import PracticeSubscription
    profile = UserProfile.objects.select_for_update().filter(user=user,role='owner').first()
    if not profile or not user.is_active:
        raise ValidationError('Only the practice owner can redeem this offer.')
    practice = Practice.objects.select_for_update().get(pk=profile.practice_id)
    if (not practice.subscription_required or practice.free_access_kind != 'trial' or FoundingTherapistInvitation.objects.filter(practice=practice).exists()
            or PracticeSubscription.objects.filter(practice=practice).exists()):
        raise ValidationError('This offer is for a new practice or an ordinary trial without a subscription.')
    if practice.user_profiles.filter(user__is_active=True,role__in=['owner','admin','therapist']).count() != 1:
        raise ValidationError('This offer includes one internal user. Contact us about team access.')
    invitation = offer_for(code,user.email,lock=True)
    redeem_for_practice(invitation,practice,timezone.now())
    return practice


@transaction.atomic
def issue_founding_offer(email, *, rotate=False):
    """Reserve one campaign slot and return its code once, without emailing it."""
    email = email.strip().lower()
    try:
        validate_email(email)
    except ValidationError as error:
        raise ValidationError('Enter a valid email address.') from error
    # Lock the fixed fifty slots in a stable order for concurrent issuance.
    invitations = list(FoundingTherapistInvitation.objects.select_for_update().order_by('slot'))
    existing = next((item for item in invitations if item.email.casefold() == email.casefold()), None)
    if existing and (existing.redeemed_at or not rotate):
        raise ValidationError('This email already has a code. Only an unused code may be explicitly rotated.')
    invitation = existing or next((item for item in invitations if not item.email and not item.redeemed_at), None)
    if not invitation:
        raise ValidationError('All fifty places have been allocated; no code issued.')
    raw = secrets.token_hex(12).upper()
    code = 'NUVIA-' + '-'.join(raw[i:i + 4] for i in range(0, 24, 4))
    invitation.email = email
    invitation.token_hash = hashlib.sha256(normalize_code(code).encode()).hexdigest()
    invitation.expires_at = timezone.now() + timedelta(days=30)
    invitation.save(update_fields=['email', 'token_hash', 'expires_at'])
    return {
        'code': code,
        'signup_url': 'https://nuviamy.com' + reverse('signup') + '?' + urlencode({'offer': code}),
        'expires_at': invitation.expires_at.isoformat(),
        'months': 6, 'internal_users': 1, 'slot': invitation.slot,
    }
