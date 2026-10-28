"""Scoped automated incident and HTTP authorization exercises with synthetic records."""
import hashlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import time

import pyotp
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.test import TestCase, Client as Browser, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.security import security_state, new_recovery_codes
from apps.audit.models import AuditLog
from apps.appointments.models import Appointment
from apps.billing.models import Invoice
from apps.clients.models import Client
from apps.clinical.models import SessionNote, Diagnosis, TreatmentPlan
from apps.dashboard.models import SupportTicket, SupportMessage, Task
from apps.documents.models import ClientDocument
from apps.portal.models import (ClientPortalAccess, PortalConversation, ClientIntakeAssignment,
                                IntakePacketTemplate, ClientPortalRequest)
from apps.practices.models import Practice, TherapistProfile

KEY='MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA='


def evidence(name, value):
    directory=os.environ.get('OPS_DRILL_REPORT_DIR')
    if directory:
        root=Path(directory)
        if not root.is_dir() or root.stat().st_mode & 0o077:
            raise ValueError('Drill evidence requires a private existing directory.')
        fd=os.open(root/name,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(fd,'w') as output:json.dump(value,output,sort_keys=True,indent=2)


@override_settings(MFA_REQUIRED=False,MFA_PRIVILEGED_REQUIRED=True,EMAIL_TWO_STEP_REQUIRED=False,
    EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend',FIELD_ENCRYPTION_KEY=KEY,SENTRY_DSN='',
    STRIPE_SECRET_KEY='',GOOGLE_OAUTH_CLIENT_ID='',GOOGLE_OAUTH_CLIENT_SECRET='')
class TechnicalIncidentDrill(TestCase):
    def test_compromised_fixture_session_is_contained_with_evidence_and_retest(self):
        started=time.monotonic()
        events=[]
        def record(name):
            events.append({'event':name,'elapsed_seconds':round(time.monotonic()-started,6),
                           'at':timezone.now().isoformat()})
        password='Synthetic-incident-password-42!'
        user=get_user_model().objects.create_superuser('synthetic-incident-operator','ops@example.invalid',password)
        practice=Practice.objects.create(name='SYNTHETIC INCIDENT DRILL')
        UserProfile.objects.create(user=user,practice=practice,role='owner')
        patient=Client.objects.create(practice=practice,first_name='SYNTHETIC',last_name='INCIDENT')
        state=security_state(user)
        secret=pyotp.random_base32()
        state.secret=secret
        state.confirmed=True
        state.last_counter=int(time.time())//30-2
        recovery=new_recovery_codes(state)
        state.save()
        legitimate,compromised=Browser(),Browser()
        for browser in (legitimate,compromised):
            browser.force_login(user)
            session=browser.session
            session['mfa_version']=str(state.session_version)
            session.save()
        resource=reverse('clients:detail',args=[patient.pk])
        self.assertEqual(compromised.get(resource,secure=True).status_code,200)
        record('fixture_detected')
        original=list(AuditLog.objects.values('id','action','object_type','object_id','metadata','created_at'))
        original_hash=hashlib.sha256(json.dumps(original,default=str,sort_keys=True).encode()).hexdigest()
        record('evidence_preserved')
        response=legitimate.post(reverse('security_settings'),{'action':'revoke_sessions',
            'password':password,'code':pyotp.TOTP(secret).now()},secure=True)
        self.assertEqual(response.status_code,302)
        record('sessions_revoked')
        denied=compromised.get(resource,secure=True)
        self.assertEqual(denied.status_code,302)
        self.assertIn(reverse('login'),denied.url)
        self.assertNotIn('_auth_user_id',compromised.session)
        self.assertTrue(AuditLog.objects.filter(metadata__event='revoke_sessions').exists())
        record('old_session_rejected')
        user.set_password('Synthetic-rotated-password-43!')
        user.save(update_fields=['password'])
        record('fixture_password_rotated')
        old=Browser()
        self.assertEqual(old.post(reverse('login'),{'username':user.email,'password':password},secure=True).status_code,200)
        self.assertNotIn('_auth_user_id',old.session)
        record('old_password_rejected')
        replacement=Browser()
        login=replacement.post(reverse('login'),{'username':user.email,
            'password':'Synthetic-rotated-password-43!'},secure=True)
        self.assertEqual(login.status_code,302)
        self.assertIn(reverse('mfa_challenge'),login.url)
        self.assertEqual(replacement.post(reverse('mfa_challenge'),{'code':recovery[0]},secure=True).status_code,302)
        self.assertEqual(replacement.get(resource,secure=True).status_code,200)
        record('replacement_mfa_and_access_retested')
        retained=list(AuditLog.objects.filter(pk__in=[row['id'] for row in original]).values(
            'id','action','object_type','object_id','metadata','created_at'))
        self.assertEqual(hashlib.sha256(json.dumps(retained,default=str,sort_keys=True).encode()).hexdigest(),original_hash)
        with self.assertRaises(ValidationError):AuditLog.objects.filter(pk=original[0]['id']).delete()
        record('original_evidence_immutable')
        evidence('technical-incident.json',{'synthetic_only':True,'executed_by':'automated technical exercise',
            'human_response_time_measured':False,'production_modified':False,'real_notifications_sent':False,
            'notification_draft':'SIMULACRO: sesión ficticia revocada; credencial ficticia rotada; acceso revisado. No hay datos reales afectados.',
            'preserved_evidence_sha256':original_hash,'events':events,'result':'passed'})


@override_settings(MFA_REQUIRED=False,MFA_PRIVILEGED_REQUIRED=False,EMAIL_TWO_STEP_REQUIRED=False,
    EMAIL_BACKEND='django.core.mail.backends.dummy.EmailBackend',FIELD_ENCRYPTION_KEY=KEY,SENTRY_DSN='',STRIPE_SECRET_KEY='')
class HttpAuthorizationMatrix(TestCase):
    def setUp(self):
        self.media=TemporaryDirectory(prefix='nuviamy-http-matrix-')
        self.addCleanup(self.media.cleanup)
        override=override_settings(MEDIA_ROOT=self.media.name,
            STORAGES={'default':{'BACKEND':'django.core.files.storage.FileSystemStorage'},
                      'staticfiles':{'BACKEND':'django.contrib.staticfiles.storage.StaticFilesStorage'}})
        override.enable();self.addCleanup(override.disable)
        self.owner,self.practice,self.therapist=self.member('matrix-owner')
        self.foreign,self.other,self.other_therapist=self.member('matrix-foreign')
        self.patient=Client.objects.create(practice=self.practice,first_name='SYNTHETIC',last_name='OWN')
        self.target=Client.objects.create(practice=self.other,first_name='FOREIGN-CLINICAL-SENTINEL',last_name='SYNTHETIC')
        self.appointment=Appointment.objects.create(practice=self.other,client=self.target,therapist=self.other_therapist,
            starts_at=timezone.now(),ends_at=timezone.now()+timezone.timedelta(hours=1))
        self.note=SessionNote.objects.create(practice=self.other,client=self.target,therapist=self.other_therapist,
            content='FOREIGN-CLINICAL-SENTINEL')
        self.plan=TreatmentPlan.objects.create(practice=self.other,client=self.target,therapist=self.other_therapist,title='FOREIGN-CLINICAL-SENTINEL')
        self.diagnosis=Diagnosis.objects.create(practice=self.other,client=self.target,code='Z00',label='FOREIGN-CLINICAL-SENTINEL')
        self.document=ClientDocument.objects.create(practice=self.other,client=self.target,title='FOREIGN-CLINICAL-SENTINEL',
            file=ContentFile(b'FOREIGN-CLINICAL-SENTINEL',name='synthetic.txt'))
        self.invoice=Invoice.objects.create(practice=self.other,client=self.target,invoice_number='SYNTHETIC',amount='10.00')
        self.conversation=PortalConversation.objects.create(practice=self.other,client=self.target,subject='FOREIGN-CLINICAL-SENTINEL')
        self.assignment=ClientIntakeAssignment.objects.create(practice=self.other,client=self.target,
            template=IntakePacketTemplate.objects.create(practice=self.other,name='SYNTHETIC',questions=['Question']))
        self.request=ClientPortalRequest.objects.create(practice=self.other,client=self.target,category='general',
            subject='FOREIGN-CLINICAL-SENTINEL',message='FOREIGN-CLINICAL-SENTINEL')
        self.task=Task.objects.create(practice=self.other,title='FOREIGN-CLINICAL-SENTINEL',assignee=self.foreign,created_by=self.foreign)
        self.support=SupportTicket.objects.create(practice=self.other,requester=self.foreign,contact_email=self.foreign.email,topic='technical')
        SupportMessage.objects.create(ticket=self.support,body='FOREIGN-CLINICAL-SENTINEL')
        self.client.force_login(self.owner)

    def member(self,name):
        user=get_user_model().objects.create_user(name,email=name+'@example.invalid')
        practice=Practice.objects.create(name='SYNTHETIC '+name)
        UserProfile.objects.create(user=user,practice=practice,role='owner')
        therapist=TherapistProfile.objects.create(user=user,practice=practice,license_number=name,license_state='CA')
        return user,practice,therapist

    def routes(self):
        pairs=[('clients:detail',self.target.pk),('clients:edit',self.target.pk),('clients:delete',self.target.pk),
            ('appointments:edit',self.appointment.pk),('appointments:cancel',self.appointment.pk),
            ('appointments:reschedule',self.appointment.pk),('appointments:delete',self.appointment.pk),
            ('appointments:google_sync',self.appointment.pk),('clinical:edit',self.note.pk),
            ('clinical:delete',self.note.pk),('clinical:sign',self.note.pk),('clinical:addendum',self.note.pk),
            ('clinical:treatment_plan_edit',self.plan.pk),('clinical:treatment_plan_delete',self.plan.pk),
            ('clinical:diagnosis_edit',self.diagnosis.pk),('clinical:diagnosis_delete',self.diagnosis.pk),
            ('documents:download',self.document.pk),('documents:delete',self.document.pk),
            ('billing:invoice_edit',self.invoice.pk),('billing:invoice_print',self.invoice.pk),
            ('billing:invoice_delete',self.invoice.pk),('billing:invoice_publish',self.invoice.pk),
            ('intake:responses',self.assignment.pk),('intake:review',self.assignment.pk),
            ('portal_requests:status',self.request.pk),('portal_requests:conversation_detail',self.conversation.public_id),
            ('tasks_detail',self.task.pk),('tasks_status',self.task.pk),('support_request_detail',self.support.pk)]
        return [(name,reverse(name,args=[pk])) for name,pk in pairs]

    def test_cross_practice_get_and_post_do_not_disclose_or_mutate_foreign_records(self):
        outcomes=[]
        for name,url in self.routes():
            for method in ('get','post'):
                with self.subTest(view=name,method=method):
                    response=getattr(self.client,method)(url,{},secure=True)
                    self.assertIn(response.status_code,(403,404,405))
                    if not response.streaming:self.assertNotIn(b'FOREIGN-CLINICAL-SENTINEL',response.content)
                    outcomes.append({'view':name,'method':method,'status':response.status_code})
        self.assertTrue(Client.objects.filter(pk=self.target.pk).exists())
        self.assertTrue(ClientDocument.objects.filter(pk=self.document.pk).exists())
        self.assertTrue(SessionNote.objects.filter(pk=self.note.pk).exists())
        evidence('http-tenant-matrix.json',{'synthetic_only':True,'requests':outcomes,'result':'passed',
            'scope':'Listed object-level read/write routes; not every application endpoint or an independent penetration test.'})

    def test_anonymous_requests_do_not_reveal_private_resources(self):
        self.client.logout()
        for name,url in self.routes():
            with self.subTest(view=name):
                response=self.client.get(url,secure=True)
                self.assertIn(response.status_code,(302,403,404,405))
                self.assertNotIn(b'FOREIGN-CLINICAL-SENTINEL',response.content)

    def test_patient_cannot_use_other_client_invoice_forms_documents_or_messages(self):
        user=get_user_model().objects.create_user('matrix-patient')
        ClientPortalAccess.objects.create(user=user,practice=self.practice,client=self.patient)
        self.client.force_login(user)
        for name,pk in [('portal:invoice_pay',self.invoice.pk),('portal:intake_responses',self.assignment.pk),
                        ('portal:intake_complete',self.assignment.pk),('portal:conversation_detail',self.conversation.public_id),
                        ('documents:download',self.document.pk)]:
            with self.subTest(view=name):
                response=self.client.post(reverse(name,args=[pk]),{},secure=True) if name=='portal:invoice_pay' else self.client.get(reverse(name,args=[pk]),secure=True)
                self.assertIn(response.status_code,(403,404))
                self.assertNotIn(b'FOREIGN-CLINICAL-SENTINEL',response.content)
        self.assertEqual(self.client.post(reverse('practice_data_export'),secure=True).status_code,403)

    def test_positive_control_and_csrf_guard(self):
        self.assertEqual(self.client.get(reverse('clients:detail',args=[self.patient.pk]),secure=True).status_code,200)
        protected=Browser(enforce_csrf_checks=True);protected.force_login(self.owner)
        response=protected.post(reverse('clients:delete',args=[self.patient.pk]),secure=True)
        self.assertEqual(response.status_code,403)
        self.assertTrue(Client.objects.filter(pk=self.patient.pk).exists())

    def test_patient_cannot_read_another_patient_in_the_same_practice(self):
        user=get_user_model().objects.create_user('matrix-same-practice-patient')
        ClientPortalAccess.objects.create(user=user,practice=self.practice,client=self.patient)
        other_patient=Client.objects.create(practice=self.practice,first_name='OTHER-PATIENT-SENTINEL',last_name='SYNTHETIC')
        document=ClientDocument.objects.create(practice=self.practice,client=other_patient,title='OTHER-PATIENT-SENTINEL',
            file=ContentFile(b'OTHER-PATIENT-SENTINEL',name='same-practice.txt'))
        invoice=Invoice.objects.create(practice=self.practice,client=other_patient,invoice_number='SYNTHETIC-OTHER',amount='10.00')
        assignment=ClientIntakeAssignment.objects.create(practice=self.practice,client=other_patient,
            template=IntakePacketTemplate.objects.create(practice=self.practice,name='OTHER',questions=['Question']))
        conversation=PortalConversation.objects.create(practice=self.practice,client=other_patient,subject='OTHER-PATIENT-SENTINEL')
        self.client.force_login(user)
        for name,pk in [('portal:invoice_pay',invoice.pk),('portal:intake_responses',assignment.pk),
                        ('portal:intake_complete',assignment.pk),('portal:conversation_detail',conversation.public_id),
                        ('documents:download',document.pk)]:
            with self.subTest(view=name):
                response=self.client.post(reverse(name,args=[pk]),{},secure=True) if name=='portal:invoice_pay' else self.client.get(reverse(name,args=[pk]),secure=True)
                self.assertIn(response.status_code,(403,404))
                self.assertNotIn(b'OTHER-PATIENT-SENTINEL',response.content)

    def test_practice_owner_cannot_manage_platform_accounts_in_the_same_practice(self):
        for privileged_flag in ('is_staff','is_superuser'):
            for action in ('deactivate','reactivate','delete','update_permissions','resend_invitation'):
                with self.subTest(flag=privileged_flag,action=action):
                    active=action not in {'reactivate','delete'}
                    target=get_user_model().objects.create_user('platform-'+privileged_flag+'-'+action,
                        email='synthetic-platform@example.invalid',is_active=active,**{privileged_flag:True})
                    profile=UserProfile.objects.create(user=target,practice=self.practice,role='therapist',
                        permissions={'clients':{'view':True}})
                    response=self.client.post(reverse('team_member_action',args=[profile.pk]),{'action':action},secure=True)
                    self.assertEqual(response.status_code,403)
                    target.refresh_from_db();profile.refresh_from_db()
                    self.assertEqual(target.is_active,active)
                    self.assertEqual(profile.permissions,{'clients':{'view':True}})
                    self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.DENIED,
                        metadata__reason='platform_account_protected').exists())
                    page=self.client.get(reverse('team_management'),secure=True)
                    self.assertEqual(page.status_code,200)
                    self.assertNotIn(('action="'+reverse('team_member_action',args=[profile.pk])+'"').encode(),page.content)

    def test_regular_practice_admin_can_be_managed_and_changes_are_audited(self):
        target=get_user_model().objects.create_user('regular-practice-admin',email='practice-admin@example.invalid')
        profile=UserProfile.objects.create(user=target,practice=self.practice,role='admin')
        url=reverse('team_member_action',args=[profile.pk])
        for action,active,event in [('deactivate',False,'team_member_deactivated'),('reactivate',True,'team_member_reactivated')]:
            response=self.client.post(url,{'action':action},secure=True)
            self.assertEqual(response.status_code,302)
            target.refresh_from_db();self.assertEqual(target.is_active,active)
            self.assertTrue(AuditLog.objects.filter(object_id=str(target.pk),metadata__event=event).exists())
        self.client.post(url,{'action':'deactivate'},secure=True)
        target_id=target.pk
        self.assertEqual(self.client.post(url,{'action':'delete'},secure=True).status_code,302)
        self.assertFalse(get_user_model().objects.filter(pk=target_id).exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.DELETE,object_id=str(target_id),metadata__event='team_member_deleted').exists())
        colleague=get_user_model().objects.create_user('regular-therapist-permissions')
        permissions=UserProfile.objects.create(user=colleague,practice=self.practice,role='therapist')
        self.assertEqual(self.client.post(reverse('team_member_action',args=[permissions.pk]),
            {'action':'update_permissions','perm_clients_view':'on'},secure=True).status_code,302)
        changed=AuditLog.objects.get(metadata__event='team_permissions_updated')
        self.assertTrue(changed.metadata['permissions']['clients']['view'])
