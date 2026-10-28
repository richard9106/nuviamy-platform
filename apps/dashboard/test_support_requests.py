"""Synthetic support data only: storage boundaries, tenant access and admin replies."""
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core import mail
from django.core.exceptions import ImproperlyConfigured
from django.db import connection
from django.test import Client as HttpClient, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import UserProfile
from apps.audit.models import AuditLog
from apps.clients.models import Client
from apps.portal.models import ClientPortalAccess
from apps.practices.models import Practice
from .models import SupportMessage, SupportTicket

KEY = 'MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA='


@override_settings(FIELD_ENCRYPTION_KEY=KEY, MFA_REQUIRED=False,
                   MFA_PRIVILEGED_REQUIRED=False, EMAIL_TWO_STEP_REQUIRED=False,
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   SUPPORT_EMAIL='operator@example.com')
class PrivateSupportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('support-owner', email='owner@example.com')
        self.practice = Practice.objects.create(name='Synthetic practice')
        UserProfile.objects.create(user=self.user, practice=self.practice, role=UserProfile.Role.OWNER)
        self.ticket = SupportTicket.objects.create(requester=self.user, practice=self.practice,
            contact_name='Synthetic owner', contact_email=self.user.email, topic='technical')
        self.original = SupportMessage.objects.create(ticket=self.ticket, author=self.user,
            body='Synthetic confidential message')
        self.detail = reverse('support_request_detail', args=[self.ticket.pk])

    def post_request(self):
        with self.captureOnCommitCallbacks(execute=True):
            return self.client.post(reverse('support_contact'), {
                'name': 'Do not trust supplied identity', 'email': 'forged@example.com',
                'topic': 'technical', 'message': 'Private support body', 'website': ''})

    def test_owner_can_create_and_reply_without_emailing_contents(self):
        self.client.force_login(self.user)
        response = self.post_request()
        ticket = SupportTicket.objects.exclude(pk=self.ticket.pk).get()
        self.assertRedirects(response, reverse('support_request_detail', args=[ticket.pk]))
        self.assertEqual(ticket.contact_email, self.user.email)
        self.assertEqual(ticket.contact_name, self.user.get_full_name())
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.detail, {'message': '<script>private</script>',
                'is_operator': 'true', 'author': '999'})
        self.assertRedirects(response, self.detail)
        reply = self.ticket.messages.last()
        self.assertFalse(reply.is_operator)
        self.assertEqual(reply.author, self.user)
        page = self.client.get(self.detail)
        self.assertContains(page, '&lt;script&gt;private&lt;/script&gt;')
        self.assertNotContains(page, '<script>private</script>')
        self.assertIn('no-store', page['Cache-Control'])
        self.assertContains(page, 'noindex, nofollow')
        self.assertEqual(len(mail.outbox), 2)
        for email in mail.outbox:
            self.assertEqual(email.to, ['operator@example.com'])
            self.assertFalse(email.reply_to)
            self.assertNotIn('Private support body', email.body)
            self.assertNotIn('private</script>', email.body)
            self.assertNotIn(self.user.email, email.body)
        logs = AuditLog.objects.filter(object_type__startswith='dashboard.Support')
        self.assertTrue(logs.exists())
        self.assertNotIn('Private support body', str(list(logs.values('metadata'))))
        self.assertNotIn('private</script>', str(list(logs.values('metadata'))))

    def test_storage_is_encrypted_including_token_like_input(self):
        message = SupportMessage.objects.create(ticket=self.ticket, body='fernet:literal-user-input')
        with connection.cursor() as cursor:
            cursor.execute('SELECT contact_name, contact_email FROM dashboard_supportticket WHERE id = %s',
                           [self.ticket.pk.hex if connection.vendor == 'sqlite' else self.ticket.pk])
            values = cursor.fetchone()
            cursor.execute('SELECT body FROM dashboard_supportmessage WHERE id = %s', [self.original.pk])
            values += cursor.fetchone()
        for value in values:
            self.assertTrue(value.startswith('fernet:'))
            self.assertNotIn('Synthetic', value)
            self.assertNotIn(self.user.email, value)
        self.assertEqual(SupportMessage.objects.get(pk=message.pk).body, 'fernet:literal-user-input')

    @override_settings(FIELD_ENCRYPTION_KEY='')
    def test_missing_key_fails_closed(self):
        count = SupportTicket.objects.count()
        response = self.post_request()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(SupportTicket.objects.count(), count)
        with self.assertRaises(ImproperlyConfigured):
            SupportMessage.objects.create(ticket_id=self.ticket.pk, body='Never plaintext')
        self.assertFalse(mail.outbox)

    def test_wrong_key_cannot_read_body(self):
        with override_settings(FIELD_ENCRYPTION_KEY='MTExMTExMTExMTExMTExMTExMTExMTExMTExMTExMTE='):
            with self.assertRaises(ImproperlyConfigured):
                SupportMessage.objects.get(pk=self.original.pk)

    def test_public_request_stores_body_and_does_not_expose_thread(self):
        response = self.post_request()
        self.assertRedirects(response, '/help/contact/?sent=1')
        ticket = SupportTicket.objects.exclude(pk=self.ticket.pk).get()
        self.assertIsNone(ticket.requester)
        self.assertIsNone(ticket.practice)
        self.assertEqual(ticket.messages.get().body, 'Private support body')
        self.assertNotIn('Private support body', mail.outbox[0].body)
        self.assertEqual(self.client.get(reverse('support_request_detail', args=[ticket.pk])).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('support_request_detail', args=[ticket.pk])).status_code, 404)

    @patch('apps.dashboard.support_requests.EmailMessage.send', side_effect=RuntimeError('private provider payload'))
    def test_notice_failure_keeps_request_and_logs_only_generic_event(self, send):
        self.assertEqual(self.post_request().status_code, 302)
        self.assertEqual(SupportTicket.objects.count(), 2)
        entry = AuditLog.objects.get(metadata__event='support_notice_failed')
        self.assertEqual(entry.metadata, {'event': 'support_notice_failed'})

    def test_login_and_csrf_required(self):
        self.assertEqual(self.client.get(self.detail).status_code, 302)
        self.assertEqual(self.client.get(reverse('support_requests')).status_code, 302)
        csrf_client = HttpClient(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        self.assertEqual(csrf_client.post(self.detail, {'message': 'No CSRF'}).status_code, 403)
        self.assertEqual(csrf_client.post(reverse('support_contact'), {'topic': 'setup'}).status_code, 403)
        self.assertEqual(self.ticket.messages.count(), 1)

    def test_other_user_same_practice_and_other_tenant_cannot_access(self):
        other = get_user_model().objects.create_user('support-other')
        profile = UserProfile.objects.create(user=other, practice=self.practice, role=UserProfile.Role.OWNER)
        self.client.force_login(other)
        for method in ('get', 'post'):
            self.assertEqual(getattr(self.client, method)(self.detail, {'message': 'intrusion'}).status_code, 404)
        self.assertNotContains(self.client.get(reverse('support_requests')), str(self.ticket.pk))
        profile.practice = Practice.objects.create(name='Other synthetic practice')
        profile.save(update_fields=['practice'])
        self.assertEqual(self.client.get(self.detail).status_code, 404)
        # Membership moves do not disclose tickets from a former practice either.
        self.user.nuvia_profile.practice = profile.practice
        self.user.nuvia_profile.save(update_fields=['practice'])
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.detail).status_code, 404)
        self.assertEqual(self.ticket.messages.count(), 1)

    def test_patient_uses_practice_portal_and_cannot_submit_product_support(self):
        user = get_user_model().objects.create_user('support-patient')
        patient = Client.objects.create(practice=self.practice, first_name='Synthetic', last_name='Patient')
        ClientPortalAccess.objects.create(user=user, practice=self.practice, client=patient)
        self.client.force_login(user)
        self.assertContains(self.client.get(reverse('support_contact')), 'Contact your practice')
        self.assertNotContains(self.client.get(reverse('help_center')), 'href="' + reverse('support_requests') + '"')
        self.assertEqual(self.post_request().status_code, 403)
        self.assertEqual(self.client.get(reverse('support_requests')).status_code, 403)

    def test_closed_thread_cannot_accept_reply(self):
        self.ticket.status = SupportTicket.Status.CLOSED
        self.ticket.save(update_fields=['status'])
        self.client.force_login(self.user)
        response = self.client.post(self.detail, {'message': 'Not accepted'})
        self.assertContains(response, 'This request is closed')
        self.assertEqual(self.ticket.messages.count(), 1)

    def test_reply_rate_limit(self):
        self.client.force_login(self.user)
        for _ in range(20):
            self.assertEqual(self.client.post(self.detail, {}).status_code, 200)
        self.assertEqual(self.client.post(self.detail, {}).status_code, 429)

    def test_non_superuser_cannot_review_even_with_model_permissions(self):
        self.user.is_staff = True
        self.user.save(update_fields=['is_staff'])
        self.user.user_permissions.set(Permission.objects.filter(content_type__app_label='dashboard'))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('admin:dashboard_supportticket_changelist')).status_code, 403)
        self.assertEqual(self.client.get(reverse('admin:dashboard_supportticket_change', args=[self.ticket.pk])).status_code, 403)

    def test_superuser_reply_preserves_existing_message_and_emails_generic_notice(self):
        operator = get_user_model().objects.create_superuser('support-operator', 'ops@example.com', 'SyntheticPass123!')
        self.client.force_login(operator)
        url = reverse('admin:dashboard_supportticket_change', args=[self.ticket.pk])
        self.assertContains(self.client.get(url), 'Synthetic confidential message')
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(url, {'status': 'open', '_save': 'Save',
                'messages-TOTAL_FORMS': '2', 'messages-INITIAL_FORMS': '1',
                'messages-MIN_NUM_FORMS': '0', 'messages-MAX_NUM_FORMS': '1000',
                'messages-0-id': str(self.original.pk), 'messages-0-ticket': str(self.ticket.pk),
                'messages-0-body': 'tampered existing message',
                'messages-1-body': 'Synthetic operator response'})
        self.assertEqual(response.status_code, 302)
        self.original.refresh_from_db()
        self.assertEqual(self.original.body, 'Synthetic confidential message')
        reply = self.ticket.messages.last()
        self.assertTrue(reply.is_operator)
        self.assertEqual(reply.author, operator)
        self.assertEqual(reply.body, 'Synthetic operator response')
        self.assertEqual(mail.outbox[0].to, [self.user.email])
        self.assertNotIn(reply.body, mail.outbox[0].body)
        self.assertTrue(AuditLog.objects.filter(metadata__event='operator_support_reply').exists())
        self.assertTrue(AuditLog.objects.filter(action=AuditLog.Action.VIEW, object_type='access.admin.dashboard.SupportTicket').exists())

    @override_settings(MFA_PRIVILEGED_REQUIRED=True)
    def test_operator_review_requires_configured_privileged_mfa(self):
        operator = get_user_model().objects.create_superuser('support-mfa-operator', 'mfa@example.com', 'SyntheticPass123!')
        self.client.force_login(operator)
        response = self.client.get(reverse('admin:dashboard_supportticket_change', args=[self.ticket.pk]))
        self.assertRedirects(response, reverse('mfa_setup'), fetch_redirect_response=False)
        self.assertNotIn(self.original.body.encode(), response.content)
