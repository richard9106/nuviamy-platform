"""Production permissions approved for the NuviaMy OAuth project."""
from urllib.parse import urlsplit
from django.core.exceptions import PermissionDenied

CALENDAR_SCOPE = 'https://www.googleapis.com/auth/calendar.events.owned'
APPROVED_GRANTS = frozenset({'openid', 'email', 'https://www.googleapis.com/auth/userinfo.email', CALENDAR_SCOPE})


def require_approved_capabilities(scopes):
    if set(scopes) != {CALENDAR_SCOPE}:
        raise PermissionDenied('Only the approved Google Calendar permission is available.')


def grants_are_approved(scopes):
    granted = set(scopes)
    return CALENDAR_SCOPE in granted and granted <= APPROVED_GRANTS


def require_approved_api_url(url):
    parsed = urlsplit(url)
    events = '/calendar/v3/calendars/primary/events'
    if not (parsed.scheme == 'https' and parsed.netloc == 'www.googleapis.com'
            and (parsed.path == events or parsed.path.startswith(events + '/'))):
        raise PermissionDenied('This Google capability is not currently available.')
