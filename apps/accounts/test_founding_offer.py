import hashlib
import json
from datetime import datetime, timedelta, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import IntegrityError, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.forms import PracticeSignupForm
from apps.accounts.models import UserProfile
from apps.billing.access import subscription_access
from apps.billing.models import PracticeSubscription
from apps.practices.models import FoundingTherapistInvitation, EarlyAccessInvitation, Practice
from apps.practices.founding_offer import offer_for, normalize_code, redeem_existing_offer, six_months_after


@override_settings(MFA_REQUIRED=False,EMAIL_TWO_STEP_REQUIRED=False)
class FoundingOfferTests(TestCase):
    def legal_payload(self,**kwargs):
        from apps.accounts.test_legal_acceptance import LegalAcceptanceTests
        return LegalAcceptanceTests().payload(**kwargs)

    def issue(self,email='founding@example.invalid',**kwargs):
        out=StringIO();call_command('issue_founding_therapist_invitation',email,stdout=out,**kwargs)
        return json.loads(out.getvalue())

    def payload(self,**kwargs):
        return self.legal_payload(email='founding@example.invalid',**kwargs)

    def owner(self,email='founding@example.invalid'):
        practice=Practice.objects.create(name='Synthetic practice',subscription_required=True,
            free_trial_started_at=timezone.now()-timedelta(days=10),free_trial_ends_at=timezone.now()+timedelta(days=20))
        user=get_user_model().objects.create_user('founding-fixture',email=email)
        UserProfile.objects.create(user=user,practice=practice,role='owner')
        return user,practice

    def test_twenty_slots_are_seeded_and_old_campaign_is_unchanged(self):
        self.assertEqual(FoundingTherapistInvitation.objects.count(),20)
        self.assertEqual(EarlyAccessInvitation.objects.count(),10)
        with self.assertRaises(IntegrityError), transaction.atomic():
            FoundingTherapistInvitation.objects.create(slot=21,token_hash='invalid-extra-slot',expires_at=timezone.now())

    def test_command_outputs_private_code_and_hash_only_storage(self):
        data=self.issue()
        invitation=offer_for(data['code'],'FOUNDING@example.invalid')
        self.assertNotEqual(invitation.token_hash,data['code'])
        self.assertEqual(invitation.token_hash,hashlib.sha256(normalize_code(data['code']).encode()).hexdigest())
        self.assertEqual(data['months'],6)
        self.assertIn('offer=',data['signup_url'])
        self.assertEqual(invitation,offer_for(data['code'].lower().replace('-',' ')))

    def test_no_reassignment_accidental_rotation_or_unlimited_places(self):
        data=self.issue()
        with self.assertRaises(CommandError):self.issue()
        rotated=self.issue(rotate=True)
        with self.assertRaises(ValidationError):offer_for(data['code'])
        for i in range(19):self.issue(f'fixture-{i}@example.invalid')
        with self.assertRaises(CommandError):self.issue('overflow@example.invalid')
        self.assertEqual(FoundingTherapistInvitation.objects.exclude(email='').count(),20)

    def test_six_calendar_months_clip_month_end_and_keep_time(self):
        start=datetime(2026,8,31,16,45,tzinfo=dt_timezone.utc)
        self.assertEqual(six_months_after(start),datetime(2027,2,28,16,45,tzinfo=dt_timezone.utc))

    def test_signup_applies_six_months_without_stripe_or_changing_trial(self):
        data=self.issue()
        form=PracticeSignupForm(self.payload(offer_code=data['code']))
        self.assertTrue(form.is_valid(),form.errors)
        with patch('stripe.checkout.Session.create') as stripe:
            user=form.save()
        practice=user.nuvia_profile.practice
        self.assertEqual(practice.free_trial_ends_at,six_months_after(practice.free_trial_started_at))
        self.assertEqual(subscription_access(practice)['free_access'],'early_access')
        stripe.assert_not_called()
        self.assertFalse(PracticeSubscription.objects.filter(practice=practice).exists())
        with self.assertRaises(ValidationError):offer_for(data['code'])
        with patch('apps.billing.access.timezone.now',return_value=practice.free_trial_ends_at):
            self.assertEqual(subscription_access(practice)['mode'],'readonly')
        normal=PracticeSignupForm(self.legal_payload(email='normal@example.invalid',license_number='normal'))
        self.assertTrue(normal.is_valid(),normal.errors)
        normal_practice=normal.save().nuvia_profile.practice
        self.assertEqual(normal_practice.free_trial_ends_at-normal_practice.free_trial_started_at,timedelta(days=30))

    def test_wrong_email_expiry_and_both_codes_cannot_create_accounts(self):
        data=self.issue('other@example.invalid')
        for code in (data['code'],'NUVIA-INVALID'):
            form=PracticeSignupForm(self.payload(offer_code=code))
            self.assertFalse(form.is_valid())
            self.assertIn('offer_code',form.errors)
        form=PracticeSignupForm(self.payload(offer_code=data['code'],invitation='another-invitation'))
        self.assertFalse(form.is_valid())
        self.assertFalse(Practice.objects.exists())
        FoundingTherapistInvitation.objects.filter(email='other@example.invalid').update(expires_at=timezone.now()-timedelta(seconds=1))
        with self.assertRaises(ValidationError):offer_for(data['code'])

    def test_consumption_race_and_failed_signup_roll_back_everything(self):
        data=self.issue()
        form=PracticeSignupForm(self.payload(offer_code=data['code']))
        self.assertTrue(form.is_valid(),form.errors)
        with patch('apps.accounts.forms.TherapistProfile.objects.create',side_effect=ValidationError('Synthetic failure')):
            with self.assertRaises(ValidationError):form.save()
        self.assertFalse(Practice.objects.exists())
        self.assertIsNone(offer_for(data['code']).redeemed_at)
        FoundingTherapistInvitation.objects.filter(email='founding@example.invalid').update(redeemed_at=timezone.now())
        with self.assertRaises(ValidationError):form.save()
        self.assertFalse(Practice.objects.exists())

    def test_existing_owner_redeems_only_once_from_profile(self):
        data=self.issue();user,practice=self.owner()
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('profile_settings')),'Apply offer code')
        self.assertEqual(self.client.get(reverse('redeem_founding_offer')).status_code,405)
        response=self.client.post(reverse('redeem_founding_offer'),{'offer_code':data['code']})
        self.assertEqual(response.status_code,302)
        practice.refresh_from_db()
        self.assertEqual(practice.free_trial_ends_at,six_months_after(practice.free_trial_started_at))
        self.assertEqual(practice.free_access_kind,'early_access')
        with self.assertRaises(ValidationError):redeem_existing_offer(user,data['code'])

    def test_existing_paid_team_and_legacy_access_cannot_be_overwritten(self):
        data=self.issue();user,practice=self.owner()
        for reason in ('paid','team','legacy'):
            with self.subTest(reason=reason),transaction.atomic():
                sid=transaction.savepoint()
                if reason=='paid':PracticeSubscription.objects.create(practice=practice,status='active')
                elif reason=='team':
                    other=get_user_model().objects.create_user('team-fixture')
                    UserProfile.objects.create(user=other,practice=practice,role='therapist')
                else:
                    Practice.objects.filter(pk=practice.pk).update(free_access_kind='early_access')
                with self.assertRaises(ValidationError):redeem_existing_offer(user,data['code'])
                transaction.savepoint_rollback(sid)
        self.assertIsNone(offer_for(data['code']).redeemed_at)

    def test_non_owner_cannot_redeem_and_hero_does_not_advertise_invalid_code(self):
        data=self.issue();user,practice=self.owner()
        UserProfile.objects.filter(user=user).update(role='admin')
        self.client.force_login(user)
        self.assertEqual(self.client.post(reverse('redeem_founding_offer'),{'offer_code':data['code']}).status_code,403)
        self.client.logout()
        response=self.client.get(reverse('signup'),{'offer':data['code']})
        self.assertContains(response,'6 months free · one internal user')
        response=self.client.get(reverse('signup'),{'offer':'invalid'})
        self.assertContains(response,'30 days free')
        self.assertNotContains(response,'6 months free · one internal user')


from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, close_old_connections
from apps.audit.testing import ProtectedRecordsTransactionTestCase


@skipUnless(connection.vendor=='postgresql','PostgreSQL offer-lock concurrency check')
class ConcurrentFoundingOfferTests(ProtectedRecordsTransactionTestCase):
    def setUp(self):
        if not FoundingTherapistInvitation.objects.exists():
            FoundingTherapistInvitation.objects.bulk_create([
                FoundingTherapistInvitation(slot=i,token_hash=f'pending-{i}',expires_at=timezone.now()) for i in range(1,21)])

    def threaded(self,actions):
        gate=Barrier(2)
        def run(action):
            close_old_connections()
            try:
                gate.wait(timeout=10)
                return action()
            finally:close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool:return list(pool.map(run,actions))

    def test_concurrent_issuance_uses_different_slots(self):
        def issue(email):
            out=StringIO();call_command('issue_founding_therapist_invitation',email,stdout=out)
            return json.loads(out.getvalue())['slot']
        results=self.threaded([lambda:issue('first@example.invalid'),lambda:issue('second@example.invalid')])
        self.assertEqual(set(results),{1,2})

    def test_one_code_cannot_be_redeemed_by_two_practices(self):
        output=StringIO();call_command('issue_founding_therapist_invitation','owner@example.invalid',stdout=output)
        code=json.loads(output.getvalue())['code']
        users=[]
        for i in range(2):
            p=Practice.objects.create(name=f'Synthetic concurrent {i}')
            u=get_user_model().objects.create_user(f'owner-{i}',email='owner@example.invalid')
            UserProfile.objects.create(practice=p,user=u,role='owner');users.append(u.pk)
        def redeem(pk):
            try:
                redeem_existing_offer(get_user_model().objects.get(pk=pk),code)
                return True
            except ValidationError:return False
        results=self.threaded([lambda:redeem(users[0]),lambda:redeem(users[1])])
        self.assertEqual(sorted(results),[False,True])
        self.assertEqual(FoundingTherapistInvitation.objects.filter(redeemed_at__isnull=False).count(),1)
        self.assertEqual(Practice.objects.filter(free_access_kind='early_access').count(),1)
