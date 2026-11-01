from django.core import mail
from django.db import connection
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.practices.models import FoundingTherapistInvitation
from .models import SupportTicket


@override_settings(FIELD_ENCRYPTION_KEY='MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=',
                   EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
                   SUPPORT_EMAIL='operator@example.invalid')
class FoundingApplicationTests(TestCase):
    def payload(self, **changes):
        data = {'name': 'Synthetic applicant', 'email': 'synthetic@example.invalid',
                'practice_name': 'Synthetic practice', 'country': 'United States',
                'profession': 'therapist', 'contact_permission': 'on', 'website': ''}
        data.update(changes)
        return data

    def test_public_request_is_private_and_does_not_allocate_an_invitation(self):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse('founding_therapists'), self.payload(
                topic='billing', message='Untrusted free text', requester='999'))
        self.assertRedirects(response, '/founding-therapists/?sent=1')
        ticket = SupportTicket.objects.get()
        self.assertEqual(ticket.topic, 'early_access')
        self.assertIsNone(ticket.practice_id)
        self.assertIsNone(ticket.requester_id)
        self.assertEqual(ticket.contact_email, 'synthetic@example.invalid')
        self.assertIn('United States', ticket.messages.get().body)
        self.assertNotIn('Untrusted free text', ticket.messages.get().body)
        self.assertFalse(FoundingTherapistInvitation.objects.exclude(email='').exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertNotIn('synthetic@example.invalid', mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].to, ['operator@example.invalid'])
        with connection.cursor() as cursor:
            cursor.execute('SELECT contact_email FROM dashboard_supportticket')
            self.assertNotIn('synthetic@example.invalid', str(cursor.fetchone()[0]))

    def test_permission_and_honeypot_are_enforced(self):
        for changes in [{'contact_permission': ''}, {'website': 'bot'}, {'email': 'invalid'}]:
            response = self.client.post(reverse('founding_therapists'), self.payload(**changes))
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form'].errors)
        self.assertFalse(SupportTicket.objects.exists())

    def test_csrf_and_shared_contact_limit(self):
        self.assertEqual(Client(enforce_csrf_checks=True).post(
            reverse('founding_therapists'), self.payload()).status_code, 403)
        for _ in range(5):
            self.client.post(reverse('support_contact'), {})
        self.assertEqual(self.client.post(reverse('founding_therapists'), self.payload()).status_code, 429)
        self.assertFalse(SupportTicket.objects.exists())

    def test_public_banner_and_confirmation(self):
        page = self.client.get(reverse('home'))
        self.assertContains(page, '50 places')
        self.assertContains(page, reverse('founding_therapists'))
        form_page = self.client.get(reverse('founding_therapists'))
        self.assertContains(form_page, 'No card required')
        self.assertNotContains(form_page, 'data-founding-offer')
        confirmed = self.client.get(reverse('founding_therapists')+'?sent=1')
        self.assertContains(confirmed, 'Application received')
        self.assertContains(confirmed, 'noindex,follow')
        self.assertIn('no-store', confirmed['Cache-Control'])

    def test_closed_offer_does_not_collect_new_requests(self):
        for invitation in FoundingTherapistInvitation.objects.all():
            invitation.email = f'allocated-{invitation.slot}@example.invalid'
            invitation.save(update_fields=['email'])
        page = self.client.get(reverse('founding_therapists'))
        self.assertContains(page, 'All 50 invitations have been allocated')
        self.assertNotContains(page, 'name="email"')
        response = self.client.post(reverse('founding_therapists'), self.payload())
        self.assertEqual(response.status_code, 200)
        self.assertFalse(SupportTicket.objects.exists())
