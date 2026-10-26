from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.test import Client, RequestFactory, SimpleTestCase, override_settings
from django.urls import path
from django.views.defaults import page_not_found, server_error


def failing_page(request):
    raise RuntimeError('Private internal exception details')


# Isolated test URLconf: never expose an intentional error route in production.
urlpatterns = [path('failure/', failing_page)]


@override_settings(DEBUG=False, ALLOWED_HOSTS=['testserver'], SECURE_SSL_REDIRECT=False)
class ErrorPageTests(SimpleTestCase):
    def test_missing_url_returns_branded_404_without_reflecting_request_details(self):
        response = self.client.get('/missing-page-for-error-test/', {'token': 'private-token'})
        self.assertContains(response, 'NuviaMy', status_code=404)
        self.assertContains(response, "Let's get you back on track.", status_code=404)
        self.assertContains(response, 'name="robots" content="noindex,follow"', status_code=404)
        self.assertNotContains(response, 'private-token', status_code=404)
        self.assertNotContains(response, 'missing-page-for-error-test', status_code=404)
        self.assertTemplateUsed(response, '404.html')

    @override_settings(ROOT_URLCONF=__name__)
    def test_unhandled_exception_returns_branded_500_without_exception_details(self):
        response = Client(raise_request_exception=False).get('/failure/')
        self.assertContains(response, 'Something went wrong on our side.', status_code=500)
        self.assertContains(response, 'name="robots" content="noindex,follow"', status_code=500)
        self.assertNotContains(response, 'Private internal exception details', status_code=500)
        self.assertNotContains(response, 'Traceback', status_code=500)
        self.assertTemplateUsed(response, '500.html')

    def test_500_renders_without_request_processors_or_external_assets(self):
        request = RequestFactory().get('/failure/')
        with patch('apps.portal.context_processors.portal_request_badge', side_effect=RuntimeError('Database unavailable')):
            response = server_error(request)
        self.assertEqual(response.status_code, 500)
        html = response.content.decode()
        self.assertNotIn('<script', html)
        self.assertNotIn('<link', html)
        self.assertIn('<style>', html)
        self.assertIn('href="/"', html)
        self.assertIn('href="/help/contact/"', html)

    def test_default_handlers_keep_status_and_recovery_links_for_head_and_get(self):
        request = RequestFactory().get('/missing/')
        request.user = AnonymousUser()
        for handler, args, status in [(page_not_found, [Exception('Private details')], 404), (server_error, [], 500)]:
            response = handler(request, *args)
            self.assertEqual(response.status_code, status)
            self.assertContains(response, 'href="/help/"', status_code=status)
            self.assertNotContains(response, 'Private details', status_code=status)
        response = self.client.head('/missing-page-for-error-test/')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content, b'')
