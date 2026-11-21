from types import SimpleNamespace
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, TestCase, override_settings
from django.urls import resolve, reverse
from django.contrib.auth import get_user_model
from apps.accounts.models import UserProfile
from apps.clients.models import Client
from apps.practices.models import Practice
from .form_drawers import WorkspaceFormDrawerMiddleware


class FormDrawerHeaderTests(TestCase):
    def response(self,path,response=None,client=False,authenticated=True,method='get',**headers):
        request=getattr(RequestFactory(),method)(path,**headers)
        request.user=SimpleNamespace(is_authenticated=authenticated,nuvia_profile=SimpleNamespace(role='client') if client else None,client_portal_access=None)
        request.resolver_match=resolve(request.path)
        response=response or HttpResponse('<form></form>')
        response['X-Frame-Options']='DENY'
        return WorkspaceFormDrawerMiddleware(lambda _:response)(request)

    def test_same_origin_framing_is_opt_in_and_limited_to_staff_editor_routes(self):
        self.assertEqual(self.response('/clients/new/')['X-Frame-Options'],'DENY')
        editor=self.response('/clients/new/?_workspace_drawer=1')
        self.assertEqual(editor['X-Frame-Options'],'SAMEORIGIN')
        self.assertIn("frame-ancestors 'self'",editor['Content-Security-Policy'])
        self.assertEqual(editor['Cache-Control'],'no-store')
        self.assertEqual(self.response('/clients/new/?_workspace_drawer=1',client=True)['X-Frame-Options'],'DENY')
        self.assertEqual(self.response('/clients/new/?_workspace_drawer=1',authenticated=False)['X-Frame-Options'],'DENY')
        for path in ['/login/','/accounts/security/setup/','/portal/my-information/','/clinical-notes/notes/1/sign/','/billing/subscription/']:
            with self.subTest(path=path):
                self.assertEqual(self.response(path+'?_workspace_drawer=1')['X-Frame-Options'],'DENY')

    def test_redirect_bridge_preserves_destination_without_allowing_external_urls(self):
        response=self.response('/clients/new/?_workspace_drawer=1',HttpResponseRedirect('/clients/1/'))
        self.assertEqual(response.status_code,200)
        self.assertContains(response,'data-workspace-drawer-redirect="/clients/1/"')
        self.assertIn("default-src 'none'",response['Content-Security-Policy'])
        self.assertEqual(self.response('/clients/new/?_workspace_drawer=1',HttpResponseRedirect('https://other.example/')).status_code,302)

    def test_iframe_post_validation_keeps_the_form_but_csrf_errors_stay_protected(self):
        response=self.response('/clients/new/',method='post',HTTP_SEC_FETCH_DEST='iframe')
        self.assertEqual(response['X-Frame-Options'],'SAMEORIGIN')
        response=self.response('/clients/new/?_workspace_drawer=1',HttpResponse('CSRF failed',status=403))
        self.assertEqual(response['X-Frame-Options'],'DENY')


@override_settings(MFA_REQUIRED=False,MFA_PRIVILEGED_REQUIRED=False,EMAIL_TWO_STEP_REQUIRED=False)
class FormDrawerWorkflowTests(TestCase):
    def setUp(self):
        self.practice=Practice.objects.create(name='Fictional drawer practice')
        self.user=get_user_model().objects.create_user('drawer-owner')
        UserProfile.objects.create(user=self.user,practice=self.practice,role=UserProfile.Role.OWNER)
        self.client.force_login(self.user)

    def test_validation_and_success_use_existing_scoped_form_processing(self):
        response=self.client.post(reverse('clients:create'),{'status':'active'},HTTP_SEC_FETCH_DEST='iframe')
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(response['X-Frame-Options'],'SAMEORIGIN')
        response=self.client.post(reverse('clients:create'),{'first_name':'Panel','last_name':'Example','status':'active','open_workspace':'1'},HTTP_SEC_FETCH_DEST='iframe')
        record=Client.objects.get(practice=self.practice)
        self.assertContains(response,'data-workspace-drawer-redirect="'+reverse('clients:detail',args=[record.pk])+'"')
        self.assertEqual(Client.objects.count(),1)
        self.assertNotContains(response,'<script')

    def test_normal_navigation_remains_a_full_page_redirect(self):
        response=self.client.post(reverse('clients:create'),{'first_name':'Full','last_name':'Page','status':'active'})
        self.assertEqual(response.status_code,302)
