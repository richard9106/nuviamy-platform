import json
import tempfile
import uuid
from io import BytesIO
from unittest import skipUnless
from unittest.mock import patch
from PIL import Image
from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.export import build_export_data
from apps.audit.models import AuditLog
from apps.clients.models import Client
from apps.documents.models import ClientDocument
from apps.practices.models import Practice
from .models import (ClientIntakeAssignment, ClientIntakeSignature, ClientPortalAccess,
                     IntakePacketTemplate, PortalProfileSubmission)


@override_settings(MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False,
                   FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode())
class PortalInformationAndSignatureTests(TestCase):
    def setUp(self):
        self.practice = Practice.objects.create(name='Fictional portal practice')
        self.other = Practice.objects.create(name='Other practice')
        self.owner = get_user_model().objects.create_user('portal-owner')
        UserProfile.objects.create(user=self.owner, practice=self.practice, role=UserProfile.Role.OWNER)
        self.patient = Client.objects.create(practice=self.practice, first_name='Alex', last_name='Demo', email='old@example.test')
        self.user = get_user_model().objects.create_user('portal-patient', email='login@example.test')
        UserProfile.objects.create(user=self.user, practice=self.practice, role=UserProfile.Role.CLIENT)
        self.access = ClientPortalAccess.objects.create(practice=self.practice, client=self.patient, user=self.user)
        self.client.force_login(self.user)
        self.template = IntakePacketTemplate.objects.create(practice=self.practice, name='Practice-authored example',
            description='Fictional practice text for the client to review.', questions=['Example question?'], requires_signature=True)
        self.assignment = ClientIntakeAssignment.objects.create(practice=self.practice, client=self.patient, template=self.template)
        self.url = reverse('portal:intake_complete', args=[self.assignment.pk])
        self.directory = tempfile.TemporaryDirectory()
        self.storage_override = override_settings(MEDIA_ROOT=self.directory.name, STORAGES={
            'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
            'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
        self.storage_override.enable()
        self.addCleanup(self.storage_override.disable)
        self.addCleanup(self.directory.cleanup)

    def profile_data(self, **changes):
        data={'first_name':'Alex','last_name':'Updated','phone_type':'mobile', 'email':'contact@example.test',
              'confirm':'on','submission_key':str(uuid.uuid4())}
        data.update(changes)
        return data

    def png(self):
        stream=BytesIO()
        Image.new('RGB',(12,12),'white').save(stream,format='PNG')
        return SimpleUploadedFile('insurance.png',stream.getvalue(),content_type='image/png')

    def review(self, **changes):
        data={'question_0':'Fictional answer'}
        data.update(changes)
        response=self.client.post(self.url,data)
        self.assertEqual(response.status_code,200)
        self.assertTemplateUsed(response,'portal/intake_signature_review.html')
        return response.context['signature_review']

    def sign(self, token, **changes):
        data={'question_0':'Fictional answer','action':'sign','signature_review':token,'signer_name':'Alex Demo','consent':'on'}
        data.update(changes)
        return self.client.post(self.url,data)

    def test_profile_preview_submission_and_staff_apply_do_not_change_login(self):
        response=self.client.get(reverse('portal:profile'))
        self.assertContains(response,'Review &amp; continue')
        self.assertNotContains(response,'Other practice')
        data=self.profile_data()
        self.assertEqual(self.client.post(reverse('portal:profile'),data).status_code,302)
        submission=PortalProfileSubmission.objects.get()
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.last_name,'Demo')
        self.assertFalse(self.patient.email_reminders_allowed)
        self.assertEqual(submission.submitted_details['last_name'],'Updated')
        with connection.cursor() as cursor:
            cursor.execute('SELECT details FROM portal_portalprofilesubmission WHERE id=%s',[submission.pk])
            self.assertTrue(cursor.fetchone()[0].startswith('fernet:'))
        self.client.post(reverse('portal:profile'),data)
        self.assertEqual(PortalProfileSubmission.objects.count(),1)
        self.client.force_login(self.owner)
        url=reverse('clients:profile_submission',args=[self.patient.pk,submission.pk])
        self.assertContains(self.client.get(url),'contact@example.test')
        self.assertEqual(self.client.post(url,{'action':'apply','confirm':'on'}).status_code,302)
        self.patient.refresh_from_db(); self.user.refresh_from_db(); submission.refresh_from_db()
        self.assertEqual(self.patient.last_name,'Updated')
        self.assertEqual(self.patient.email,'contact@example.test')
        self.assertEqual(self.user.email,'login@example.test')
        self.assertEqual(submission.status,'applied')
        export=build_export_data(self.practice,'clinical')
        self.assertEqual(export['profile_submissions'][0]['id'],submission.pk)
        event=AuditLog.objects.filter(object_type='portal.PortalProfileSubmission').first()
        self.assertNotIn('contact@example.test',str(event.metadata))

    def test_profile_files_are_validated_private_scoped_and_not_duplicated(self):
        data=self.profile_data(insurance_front=self.png())
        self.client.post(reverse('portal:profile'),data)
        document=ClientDocument.objects.get()
        self.assertTrue(document.visible_to_client)
        self.assertEqual(document.client,self.patient)
        self.assertNotIn('insurance.png',document.file.name)
        self.assertEqual(document.content_type,'image/png')
        self.assertEqual(self.client.get(reverse('documents:download',args=[document.pk])).status_code,200)
        invalid=self.client.post(reverse('portal:profile'),self.profile_data(insurance_back=SimpleUploadedFile('bad.png',b'not an image')))
        self.assertEqual(invalid.status_code,200)
        self.assertTrue(invalid.context['form'].errors)
        self.assertEqual(ClientDocument.objects.count(),1)
        self.client.force_login(self.owner)
        wrong=Client.objects.create(practice=self.other,first_name='Other',last_name='Patient')
        submission=PortalProfileSubmission.objects.get()
        self.assertEqual(self.client.get(reverse('clients:profile_submission',args=[wrong.pk,submission.pk])).status_code,404)

    def test_profile_requires_confirmation_and_cannot_set_staff_or_billing_fields(self):
        url=reverse('portal:profile')
        response=self.client.post(url,self.profile_data(confirm=''))
        self.assertTrue(response.context['form'].errors)
        self.assertFalse(PortalProfileSubmission.objects.exists())
        self.client.post(url,self.profile_data(is_staff='on',insurance_copay='999',role='owner',email_reminders_allowed='on'))
        self.user.refresh_from_db();self.patient.refresh_from_db()
        self.assertFalse(self.user.is_staff)
        self.assertEqual(self.user.nuvia_profile.role,UserProfile.Role.CLIENT)
        self.assertIsNone(self.patient.insurance_copay)
        self.assertTrue(self.patient.email_reminders_allowed)
        self.access.is_active=False;self.access.save()
        self.assertEqual(self.client.get(url).status_code,403)

    def test_insurance_review_uses_enabled_payer_and_preserves_financial_allocations(self):
        from decimal import Decimal
        from apps.billing.models import InsurancePayer
        payer=InsurancePayer.objects.create(practice=self.practice,name='Fictional accepted payer')
        self.patient.insurance_copay=Decimal('15')
        self.patient.save()
        self.client.post(reverse('portal:profile'),self.profile_data(insurance_payer=payer.pk,
            insurance_member_id='DEMO-123',insurance_group_id='DEMO-GROUP'))
        submission=PortalProfileSubmission.objects.get()
        self.assertEqual(submission.submitted_details['insurance_payer_name'],payer.name)
        self.assertEqual(submission.submitted_details['insurance_group_id'],'DEMO-GROUP')
        self.assertEqual(self.client.get(reverse('clients:profile_submission',args=[self.patient.pk,submission.pk])).status_code,403)
        self.client.force_login(self.owner)
        review_url=reverse('clients:profile_submission',args=[self.patient.pk,submission.pk])
        self.assertContains(self.client.get(review_url),payer.name)
        self.client.post(review_url,{'action':'apply','confirm':'on'})
        self.patient.refresh_from_db()
        self.assertEqual(self.patient.insurance_payer,payer)
        self.assertEqual(self.patient.billing_type,'insurance')
        self.assertEqual(self.patient.insurance_member_id,'DEMO-123')
        self.assertEqual(self.patient.insurance_copay,Decimal('15'))

    def test_email_reminder_opt_out_blocks_delivery(self):
        from datetime import timedelta
        from apps.practices.models import TherapistProfile
        from apps.appointments.models import Appointment
        from apps.appointments.reminders import send_appointment_reminder, due_reminder_appointments
        therapist=TherapistProfile.objects.create(practice=self.practice,user=self.owner)
        start=timezone.now()+timedelta(hours=2)
        appointment=Appointment.objects.create(practice=self.practice,client=self.patient,therapist=therapist,
            starts_at=start,ends_at=start+timedelta(minutes=50))
        self.patient.email_reminders_allowed=False
        self.patient.save()
        with patch('apps.appointments.reminders.send_gmail_message') as sender:
            self.assertFalse(send_appointment_reminder(appointment))
            sender.assert_not_called()
        self.assertFalse(due_reminder_appointments().filter(pk=appointment.pk).exists())

    def test_signature_preview_is_not_a_signature_and_edit_keeps_answers(self):
        self.review()
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status,'assigned')
        self.assertFalse(ClientIntakeSignature.objects.exists())
        response=self.client.post(self.url,{'question_0':'Changed draft','action':'edit_answers'})
        self.assertTemplateUsed(response,'portal/intake_form.html')
        self.assertContains(response,'Changed draft')
        self.client.post(self.url,{'question_0':'Saved draft','action':'save_draft'})
        self.assertFalse(ClientIntakeSignature.objects.exists())

    def test_signature_binds_content_and_preserves_receipt_and_export(self):
        token=self.review()
        self.assertEqual(self.sign(token).status_code,302)
        signature=ClientIntakeSignature.objects.get()
        self.assertEqual(signature.signed_by,self.user)
        self.assertEqual(signature.relationship,'self')
        self.assignment.refresh_from_db()
        self.assertEqual(self.assignment.status,'submitted')
        self.assertEqual(self.sign(token).status_code,404)
        receipt=self.client.get(reverse('portal:intake_responses',args=[self.assignment.pk]))
        self.assertContains(receipt,'Alex Demo')
        self.assertContains(receipt,'Electronic signature')
        self.user.first_name='New profile name';self.user.save()
        self.assertContains(self.client.get(reverse('portal:intake_responses',args=[self.assignment.pk])),'Alex Demo')
        for operation in (signature.delete,lambda:ClientIntakeSignature.objects.filter(pk=signature.pk).update(signer_name='Changed')):
            with self.assertRaises(ValidationError):operation()
        self.assignment.answers={'question_0':{'answer':'Replacement'}}
        with self.assertRaises(ValidationError):self.assignment.save()
        export=build_export_data(self.practice,'clinical')
        self.assertEqual(export['intake_signatures'][0]['digest'],signature.digest)
        self.assertEqual(build_export_data(self.other,'clinical')['intake_signatures'],[])

    def test_signature_rejects_changed_content_missing_consent_and_expired_token(self):
        token=self.review()
        for changes in [{'question_0':'tampered'},{'consent':''},{'signer_name':''},{'signature_review':token+'changed'}]:
            response=self.sign(token,**changes)
            self.assertEqual(response.status_code,200)
            self.assertFalse(ClientIntakeSignature.objects.exists())
        from django.core.signing import SignatureExpired
        with patch('apps.portal.signatures.signing.loads',side_effect=SignatureExpired):
            self.sign(token)
        self.assertFalse(ClientIntakeSignature.objects.exists())

    def test_snapshot_keeps_existing_assignments_unsigned(self):
        previous=ClientIntakeAssignment.objects.create(practice=self.practice,client=self.patient,template=self.template,
            template_snapshot={'name':'Historical','questions':['Original question?']})
        self.assertFalse(previous.requires_signature)
        self.assertEqual(self.client.post(reverse('portal:intake_complete',args=[previous.pk]),{'question_0':'Legacy answer'}).status_code,302)
        self.assertFalse(ClientIntakeSignature.objects.exists())

    def test_signing_other_client_form_is_denied(self):
        other_client=Client.objects.create(practice=self.practice,first_name='Other',last_name='Client')
        other_assignment=ClientIntakeAssignment.objects.create(practice=self.practice,client=other_client,template=self.template)
        url=reverse('portal:intake_complete',args=[other_assignment.pk])
        self.assertEqual(self.client.get(url).status_code,404)
        self.assertEqual(self.client.post(url,{'question_0':'Blocked'}).status_code,404)

    @skipUnless(connection.vendor=='postgresql','PostgreSQL signature guards')
    def test_database_rejects_signature_and_signed_content_mutation(self):
        self.sign(self.review())
        signature=ClientIntakeSignature.objects.get()
        statements=[('UPDATE portal_clientintakesignature SET signer_name=%s WHERE id=%s',['Other',signature.pk]),
                    ('UPDATE portal_clientintakeassignment SET answers=%s WHERE id=%s',['{}',self.assignment.pk]),
                    ('DELETE FROM portal_clientintakesignature WHERE id=%s',[signature.pk])]
        for sql,params in statements:
            with self.assertRaises(DatabaseError),transaction.atomic():
                with connection.cursor() as cursor:cursor.execute(sql,params)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.post(reverse('intake:review',args=[self.assignment.pk])).status_code,302)
