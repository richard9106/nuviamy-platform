"""Allowed scheduling origins shared by session and note workflows."""
from urllib.parse import urlsplit

from django.urls import Resolver404, resolve

from apps.accounts.access import get_practice_for_user, has_practice_permission


def session_origin(request):
    value = request.POST.get('next') or request.GET.get('next') or ''
    if not value.startswith('/') or value.startswith('//') or any(c in value for c in ('\\', '\r', '\n')):
        return None
    try:
        parsed = urlsplit(value)
        target = resolve(parsed.path)
    except (ValueError, Resolver404):
        return None
    if parsed.scheme or parsed.netloc:
        return None
    if target.view_name == 'appointments:list':
        return value
    if target.view_name == 'clients:detail' and has_practice_permission(request.user, 'clients', 'view'):
        from apps.clients.models import Client
        if Client.objects.filter(pk=target.kwargs['pk'], practice=get_practice_for_user(request.user)).exists():
            return value
    return None
