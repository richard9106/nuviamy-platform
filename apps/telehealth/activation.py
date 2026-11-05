"""Owner activation reuses the existing immutable contract evidence store."""
from pathlib import Path
from django import forms
from django.conf import settings
from django.db import transaction
from django.template.loader import render_to_string
from django.utils import timezone
from apps.accounts.contract_models import StandardAgreementAcceptance, ClinicalContractSignature
from apps.accounts.standard_agreements import AGREEMENT_VERSION, digest
from apps.accounts.legal import legal_context, PRIVACY_VERSION
from apps.audit.models import AuditLog
from apps.practices.models import Practice, ExternalIntegration

VERSION = 'telehealth-2026-11-05-v1'
CONSENT = 'I am authorized to bind this practice and electronically accept the Embedded Video Processing Addendum. I acknowledge the Privacy Notice and the regional and excluded-data restrictions.'


def text():
    return (Path(__file__).parent/'agreements'/f'{VERSION}.txt').read_text()


def accepted(practice_id):
    return StandardAgreementAcceptance.objects.filter(practice_id=practice_id, version=VERSION).first()


def base_ready(practice_id):
    return (StandardAgreementAcceptance.objects.filter(practice_id=practice_id, version=AGREEMENT_VERSION).exists()
            or ClinicalContractSignature.objects.filter(bundle__request__practice_id=practice_id).exists())


def available(practice_id):
    return settings.TELEHEALTH_ENABLED and (settings.TELEHEALTH_GENERAL_AVAILABLE or practice_id in settings.TELEHEALTH_PRACTICE_IDS)


def offer():
    return {'telehealth': text(), 'privacy': render_to_string('marketing/privacy_policy.html',legal_context(None))}


class VideoActivationForm(forms.Form):
    representative_name = forms.CharField(max_length=200, label='Your full legal name')
    offer_digest = forms.CharField(widget=forms.HiddenInput)
    accept_scope = forms.BooleanField(label=CONSENT)
    scope_confirmed = forms.BooleanField(label='I will not use this activation for EEA clinical sessions or records excluded by the Processing Schedule without a separate approved arrangement.')

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.initial.setdefault('offer_digest',digest(offer()))

    def clean_offer_digest(self):
        value=self.cleaned_data['offer_digest']
        if value!=digest(offer()):raise forms.ValidationError('The video terms changed. Reload and review them before activating.')
        return value


@transaction.atomic
def activate(user,practice,data):
    profile=getattr(user,'nuvia_profile',None)
    if not user.is_active or not profile or profile.role!='owner' or profile.practice_id!=practice.pk:
        raise forms.ValidationError('Only this practice owner can activate video.')
    Practice.objects.select_for_update().get(pk=practice.pk)
    if not available(practice.pk) or not base_ready(practice.pk):raise forms.ValidationError('Accept your current practice agreements in Contracts first.')
    documents=offer()
    if not data.get('accept_scope') or not data.get('scope_confirmed') or data.get('offer_digest')!=digest(documents):
        raise forms.ValidationError('Review the current video scope before activating.')
    receipt=accepted(practice.pk)
    if receipt is None:
        base=StandardAgreementAcceptance.objects.filter(practice=practice,version=AGREEMENT_VERSION).first()
        signatures=list(ClinicalContractSignature.objects.filter(bundle__request__practice=practice).values_list('pk',flat=True)) if base is None else []
        snapshot={'agreement_type':'telehealth_addendum','version':VERSION,'documents':documents,'privacy_version':PRIVACY_VERSION,
                  'accepted_at':timezone.now().isoformat(),'customer':{'practice_id':practice.pk,'user_id':user.pk,'email':user.email,'representative_name':data['representative_name'].strip()},
                  'base_acceptance_id':base.pk if base else None,'base_acceptance_digest':base.digest if base else None,
                  'custom_signature_ids':[str(pk) for pk in signatures],'consent':CONSENT,'scope_confirmed':True}
        receipt=StandardAgreementAcceptance.objects.create(practice=practice,signer=user,version=VERSION,snapshot=snapshot,digest=digest(snapshot))
    ExternalIntegration.objects.update_or_create(practice=practice,provider='chime',defaults={'status':'connected','connected_at':timezone.now()})
    AuditLog.objects.create(practice=practice,actor=user,action=AuditLog.Action.CREATE,object_type='telehealth_agreement',object_id=str(receipt.pk),metadata={'event':'video_activated','agreement_digest':receipt.digest})
    return receipt
