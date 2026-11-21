"""Explicit client attestation to the frozen assigned form and reviewed answers."""
import hashlib
import json
from django import forms
from django.core import signing
from django.shortcuts import render
from .models import ClientIntakeSignature, intake_signature_digest

CONSENT = 'I reviewed this completed form and choose to sign and submit it electronically to my practice.'
SALT = 'portal.intake-review.v1'


class SignatureAttestationForm(forms.Form):
    signer_name = forms.CharField(max_length=200, min_length=2, label='Your full name')
    consent = forms.BooleanField(label=CONSENT)


def review_digest(assignment, answers):
    payload = {'assignment':assignment.pk, 'snapshot':assignment.template_snapshot, 'answers':answers}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def review_token(assignment, form, user):
    return signing.dumps({'assignment':assignment.pk,'actor':user.pk,
        'digest':review_digest(assignment,form.prepared_answers())},salt=SALT)


def valid_review(request, assignment, form):
    try:
        data=signing.loads(request.POST.get('signature_review',''),salt=SALT,max_age=600)
        return data == {'assignment':assignment.pk,'actor':request.user.pk,
                        'digest':review_digest(assignment,form.prepared_answers())}
    except (signing.BadSignature, TypeError):
        return False


def render_review(view, form, attestation=None):
    context=view.get_context_data(form=form)
    items = [{**item, 'answer': ', '.join(item['answer']) if isinstance(item['answer'], list) else item['answer']}
             for item in form.prepared_answers().values()]
    context.update(signature_form=attestation or SignatureAttestationForm(initial={
        'signer_name':view.request.user.get_full_name() or str(context['portal_client'])}),
        answer_items=items, signature_review=review_token(form.assignment,form,view.request.user))
    return render(view.request,'portal/intake_signature_review.html',context)


def create_signature(request, assignment, attestation):
    return ClientIntakeSignature.objects.create(assignment=assignment,signed_by=request.user,
        signer_name=attestation.cleaned_data['signer_name'],relationship='self',
        digest=intake_signature_digest(assignment),consent_text=CONSENT)
