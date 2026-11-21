from datetime import timedelta
from decimal import Decimal

from cryptography.fernet import Fernet
from django.contrib.auth import get_user_model
from django.core import mail
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.accounts.export import build_export_data
from apps.audit.models import AuditLog
from apps.billing.models import Invoice, Payment, InsurancePayer
from apps.portal.models import ClientIntakeAssignment, ClientPortalAccess, IntakePacketTemplate
from apps.practices.models import Practice
from .models import Client, ClientAdministrativeNote, ClientFormDelivery


@override_settings(MFA_REQUIRED=False, MFA_PRIVILEGED_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False,
                   FIELD_ENCRYPTION_KEY=Fernet.generate_key().decode(),
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
class ClientWorkspaceTests(TestCase):
    def setUp(self):
        self.practice = Practice.objects.create(name='Fictional workspace')
        self.other = Practice.objects.create(name='Other practice')
        self.user = get_user_model().objects.create_user('workspace-owner', email='owner@example.test')
        UserProfile.objects.create(user=self.user, practice=self.practice, role=UserProfile.Role.OWNER)
        self.patient = Client.objects.create(practice=self.practice, first_name='Alex', last_name='Demo', email='client@example.test')
        self.foreign = Client.objects.create(practice=self.other, first_name='Foreign', last_name='Client')
        self.template = IntakePacketTemplate.objects.create(practice=self.practice, name='Fictional private questionnaire', questions=['Example question?'])
        self.second = IntakePacketTemplate.objects.create(practice=self.practice, name='Follow-up', questions=['Example follow-up?'])
        self.url = reverse('clients:share_forms', args=[self.patient.pk])
        self.client.force_login(self.user)

    def review(self, **overrides):
        data = {'templates': [self.template.pk, self.second.pk], 'invite_portal': 'on', 'notify': 'on'}
        data.update(overrides)
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['review'], response.context['form'].errors)
        return response.context['share_token']

    def send(self, token, **overrides):
        data = {'action': 'send', 'share_token': token, 'confirm': 'on'}
        data.update(overrides)
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(self.url, data)

    def test_preview_does_not_create_access_assignments_or_email(self):
        self.review()
        self.assertFalse(ClientPortalAccess.objects.exists())
        self.assertFalse(ClientIntakeAssignment.objects.exists())
        self.assertFalse(ClientFormDelivery.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_return_from_review_preserves_selection_without_side_effects(self):
        token = self.review()
        response = self.client.post(self.url, {'action': 'edit', 'share_token': token})
        form = response.context['form']
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(set(form.cleaned_data['templates'].values_list('pk', flat=True)), {self.template.pk, self.second.pk})
        self.assertTrue(form.cleaned_data['invite_portal'])
        self.assertFalse(ClientIntakeAssignment.objects.exists())

    def test_directory_search_pagination_and_create_open_the_correct_client(self):
        for i in range(27):
            Client.objects.create(practice=self.practice, first_name='Search', last_name=f'Example {i:02d}')
        response = self.client.get(reverse('clients:list'), {'q': 'Search Example'})
        self.assertEqual(response.context['paginator'].count, 27)
        self.assertEqual(len(response.context['clients']), 25)
        response = self.client.get(reverse('clients:list'), {'q': 'Search Example', 'page': '2'})
        self.assertEqual(len(response.context['clients']), 2)
        self.assertNotContains(response, 'Foreign Client')
        response = self.client.post(reverse('clients:create'), {'first_name': 'New', 'last_name': 'Example', 'status': 'active', 'open_workspace': '1'})
        created = Client.objects.get(practice=self.practice, first_name='New')
        self.assertRedirects(response, reverse('clients:detail', args=[created.pk]))

    def test_bulk_share_invites_client_once_and_retains_original_snapshot(self):
        token = self.review()
        self.assertEqual(self.send(token).status_code, 302)
        self.assertEqual(ClientIntakeAssignment.objects.count(), 2)
        access = ClientPortalAccess.objects.get(client=self.patient)
        self.assertFalse(access.user.has_usable_password())
        self.assertFalse(access.user.is_staff)
        self.assertEqual(access.user.nuvia_profile.role, UserProfile.Role.CLIENT)
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn(self.template.name, mail.outbox[0].body)
        self.assertNotIn(self.patient.first_name, mail.outbox[0].body)
        self.assertEqual(ClientFormDelivery.objects.get().delivery_status, 'sent')
        self.send(token)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(ClientIntakeAssignment.objects.count(), 2)
        self.template.questions = ['Changed after assignment']
        self.template.save()
        self.assertEqual(ClientIntakeAssignment.objects.get(template=self.template).packet_questions, ['Example question?'])

    def test_confirmation_tamper_expiry_and_recipient_change_are_rejected(self):
        token = self.review()
        self.send(token, confirm='')
        self.send(token + 'changed')
        self.patient.email = 'changed@example.test'
        self.patient.save()
        self.send(token)
        self.assertFalse(ClientIntakeAssignment.objects.exists())
        self.assertFalse(ClientPortalAccess.objects.exists())
        from unittest.mock import patch
        from django.core.signing import SignatureExpired
        with patch('apps.clients.workspace.signing.loads', side_effect=SignatureExpired):
            self.send(token)
        self.assertFalse(ClientFormDelivery.objects.exists())

    def test_foreign_and_inactive_templates_are_not_assignable(self):
        foreign_template = IntakePacketTemplate.objects.create(practice=self.other, name='Hidden foreign form', questions=['Hidden?'])
        self.second.active = False
        self.second.save()
        for template in (foreign_template, self.second):
            response = self.client.post(self.url, {'templates': [template.pk]})
            self.assertFalse(response.context.get('review'))
        self.assertFalse(ClientIntakeAssignment.objects.exists())
        self.assertEqual(self.client.get(reverse('clients:share_forms', args=[self.foreign.pk])).status_code, 404)

    def test_template_change_after_review_requires_another_review(self):
        token = self.review()
        self.template.questions = ['Changed after review']
        self.template.save()
        response = self.send(token)
        self.assertContains(response, 'The selected forms changed.')
        self.assertFalse(ClientIntakeAssignment.objects.exists())
        self.assertFalse(ClientPortalAccess.objects.exists())

    def test_assign_without_email_and_repeat_keeps_pending_assignment(self):
        token = self.review(invite_portal='', notify='')
        self.send(token)
        second_token = self.review(invite_portal='', notify='')
        self.send(second_token)
        self.assertEqual(ClientIntakeAssignment.objects.count(), 2)
        self.assertFalse(ClientPortalAccess.objects.exists())
        self.assertEqual(len(mail.outbox), 0)

    def test_existing_account_notification_does_not_reset_password_and_reports_failure(self):
        portal_user = get_user_model().objects.create_user('existing-client', email='portal@example.test', password='test-only-password')
        access = ClientPortalAccess.objects.create(practice=self.practice, client=self.patient, user=portal_user)
        original_password = portal_user.password
        from unittest.mock import patch
        token = self.review(invite_portal='')
        with patch('apps.clients.workspace.send_mail', side_effect=RuntimeError('provider unavailable')):
            self.send(token)
        portal_user.refresh_from_db()
        self.assertEqual(portal_user.password, original_password)
        self.assertEqual(ClientFormDelivery.objects.get().delivery_status, 'failed')
        access.is_active = False
        access.save()
        response = self.client.post(self.url, {'templates': [self.template.pk], 'notify': 'on'})
        self.assertFalse(response.context.get('review'))

    def test_administrative_notes_are_encrypted_scoped_escaped_and_exported(self):
        body = '<script>alert("example")</script> Fictional call summary'
        url = reverse('clients:administrative_note', args=[self.patient.pk])
        self.assertEqual(self.client.post(url, {'content': body}).status_code, 302)
        note = ClientAdministrativeNote.objects.get()
        with connection.cursor() as cursor:
            cursor.execute('SELECT content FROM clients_clientadministrativenote WHERE id=%s', [note.pk])
            self.assertTrue(cursor.fetchone()[0].startswith('fernet:'))
        response = self.client.get(reverse('clients:detail', args=[self.patient.pk]))
        self.assertNotContains(response, body)
        self.assertContains(response, '&lt;script&gt;')
        self.assertEqual(build_export_data(self.practice, 'clinical')['administrative_notes'][0]['content'], body)
        self.assertEqual(build_export_data(self.other, 'clinical')['administrative_notes'], [])
        event = AuditLog.objects.get(object_type='clients.ClientAdministrativeNote')
        self.assertNotIn(body, str(event.metadata))
        self.assertEqual(self.client.post(reverse('clients:administrative_note', args=[self.foreign.pk]), {'content': 'blocked'}).status_code, 404)
        invalid = self.client.post(url, {'content': 'x' * 4001})
        self.assertEqual(invalid.status_code, 400)
        self.assertContains(invalid, 'x' * 4001, status_code=400)
        self.assertEqual(ClientAdministrativeNote.objects.count(), 1)

    def test_read_only_staff_cannot_add_notes_or_share_forms(self):
        profile = self.user.nuvia_profile
        profile.role = UserProfile.Role.THERAPIST
        profile.permissions = {'clients': {'view': True, 'edit': False}, 'intake': {'view': False, 'create': False}, 'billing': {'view': False}}
        profile.save()
        self.assertEqual(self.client.post(reverse('clients:administrative_note', args=[self.patient.pk]), {'content': 'blocked'}).status_code, 403)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        response = self.client.get(reverse('clients:detail', args=[self.patient.pk]), {'tab': 'forms'})
        self.assertEqual(response.context['workspace_tab'], 'overview')
        self.assertNotContains(response, 'Share forms')
        self.assertNotIn('chart_balances', response.context)

    def test_activity_filters_do_not_hide_other_client_data_in_markup(self):
        ClientAdministrativeNote.objects.create(practice=self.practice, client=self.patient, author=self.user, content='Visible entry')
        ClientAdministrativeNote.objects.create(practice=self.other, client=self.foreign, author=self.user, content='Foreign hidden entry')
        response = self.client.get(reverse('clients:detail', args=[self.patient.pk]), {'items': 'forms'})
        self.assertNotContains(response, 'Visible entry')
        self.assertNotContains(response, 'Foreign hidden entry')
        self.assertEqual(response.context['client_activity'], [])

    def test_billing_summary_splits_insurance_and_excludes_drafts_and_void(self):
        payer = InsurancePayer.objects.create(practice=self.practice, name='Fictional payer')
        invoice = Invoice.objects.create(practice=self.practice, client=self.patient, invoice_number='CHART-1', amount=Decimal('100'),
            billing_type='insurance', insurance_payer=payer, client_responsibility=Decimal('30'), status='sent')
        Payment.objects.create(practice=self.practice, client=self.patient, invoice=invoice, paid_at=timezone.now(), method='cash', amount=Decimal('10'))
        Payment.objects.create(practice=self.practice, client=self.patient, invoice=invoice, paid_at=timezone.now(), method='insurance', amount=Decimal('40'))
        for status in ('draft', 'void'):
            Invoice.objects.create(practice=self.practice, client=self.patient, invoice_number='EXCLUDED-'+status, amount=Decimal('999'), status=status)
        response = self.client.get(reverse('clients:detail', args=[self.patient.pk]))
        self.assertEqual(response.context['chart_balances'], {'client': Decimal('20'), 'insurance': Decimal('30'), 'total': Decimal('50'), 'count': 1})
