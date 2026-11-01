import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.practices.models import FoundingTherapistInvitation
from apps.practices.founding_offer import normalize_code


class Command(BaseCommand):
    help = 'Issue one of fifty personal six-month codes. Private output; sends no email.'

    def add_arguments(self,parser):
        parser.add_argument('email')
        parser.add_argument('--rotate',action='store_true',help='Explicitly replace an unused code for the same email.')

    @transaction.atomic
    def handle(self,*args,**options):
        email = options['email'].strip().lower()
        try:
            validate_email(email)
        except ValidationError as error:
            raise CommandError('Enter a valid email address.') from error
        # Lock the fixed fifty slots in a stable order for concurrent issuance.
        invitations = list(FoundingTherapistInvitation.objects.select_for_update().order_by('slot'))
        existing = next((item for item in invitations if item.email.casefold()==email.casefold()),None)
        if existing and (existing.redeemed_at or not options['rotate']):
            raise CommandError('This email already has a code. Only an unused code may be explicitly rotated.')
        invitation = existing or next((item for item in invitations if not item.email and not item.redeemed_at),None)
        if not invitation:
            raise CommandError('All fifty places have been allocated; no code issued.')
        raw = secrets.token_hex(12).upper()
        code = 'NUVIA-'+'-'.join(raw[i:i+4] for i in range(0,24,4))
        invitation.email = email
        invitation.token_hash = hashlib.sha256(normalize_code(code).encode()).hexdigest()
        invitation.expires_at = timezone.now()+timedelta(days=30)
        invitation.save(update_fields=['email','token_hash','expires_at'])
        self.stdout.write(json.dumps({'code':code,'signup_url':'https://nuviamy.com'+reverse('signup')+'?'+urlencode({'offer':code}),
            'expires_at':invitation.expires_at.isoformat(),'months':6,'internal_users':1,'slot':invitation.slot}))
