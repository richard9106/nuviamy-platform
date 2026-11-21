"""First-party framing only for explicitly enumerated staff editor endpoints."""
from django.http import HttpResponse
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from apps.accounts.access import is_client_user

FORM_DRAWER_VIEWS = {
    'clients:create', 'clients:edit',
    'appointments:create', 'appointments:edit', 'appointments:event_create', 'appointments:event_edit',
    'appointments:availability_create', 'appointments:availability_edit',
    'clinical:create', 'clinical:edit', 'clinical:diagnosis_create', 'clinical:diagnosis_edit',
    'clinical:treatment_plan_create', 'clinical:treatment_plan_edit',
    'billing:invoice_create', 'billing:invoice_edit', 'billing:package_create', 'billing:package_edit',
    'billing:payment_create', 'billing:usage_create',
    'documents:create', 'intake:template_create', 'intake:template_edit',
    'settings:package_template_create', 'settings:package_template_edit',
    'settings:insurance_payer_create', 'settings:insurance_payer_edit',
    'settings:insurance_rate_create', 'settings:insurance_rate_edit',
    'portal_settings:portal_access_create', 'portal_settings:portal_access_edit',
    'practice_settings:working_hour_create',
}


class WorkspaceFormDrawerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        name = getattr(getattr(request, 'resolver_match', None), 'view_name', '')
        framed = request.GET.get('_workspace_drawer') == '1' or request.headers.get('Sec-Fetch-Dest') == 'iframe'
        if (not framed or name not in FORM_DRAWER_VIEWS or not request.user.is_authenticated
                or is_client_user(request.user)):
            return response
        # Authorizations, CSRF, MFA and subscription checks run before this response.
        if response.status_code in (301, 302, 303, 307, 308):
            target = response.get('Location', '')
            if not url_has_allowed_host_and_scheme(target, {request.get_host()}, require_https=request.is_secure()):
                return response
            response = HttpResponse(format_html(
                '<!doctype html><html><head><meta charset="utf-8"><title>Continue</title></head>'
                '<body data-workspace-drawer-redirect="{}"><p>Continue to the next step.</p>'
                '<a href="{}" target="_top">Continue</a></body></html>', target, target))
            response['Content-Security-Policy'] = "default-src 'none'; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
        elif response.status_code != 200 or 'text/html' not in response.get('Content-Type', ''):
            return response
        response['X-Frame-Options'] = 'SAMEORIGIN'
        if 'Content-Security-Policy' not in response:
            response['Content-Security-Policy'] = "frame-ancestors 'self'"
        response['Cache-Control'] = 'no-store'
        return response
