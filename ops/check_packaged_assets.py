"""Smoke-test a fresh deployment image without generating assets or using a DB."""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

import django

django.setup()

from django.contrib.staticfiles.storage import staticfiles_storage
from django.test import Client

client = Client()
for asset in ('security-session.js', 'security.css', 'dashboard.css', 'favicon.svg', 'branding/brand.css', 'branding/door.svg', 'branding/leaves.svg', 'branding/admin.css', 'branding/manrope-variable.ttf', 'marketing/nuviamy-social-terracotta.jpg', 'diagnosis-picker.js', 'password-tools.js', 'password-tools.css', 'appointment-editor.css', 'appointment-editor.js', 'appointment-recurrence.js', 'calendar-timing.js', 'telehealth/room.js', 'telehealth/room.css', 'telehealth/chime-sdk.js'):
    url = staticfiles_storage.url(asset)
    response = client.get(url, secure=True)
    if response.status_code != 200:
        raise RuntimeError(f'Packaged asset unavailable: {asset} (HTTP {response.status_code})')
    response.close()

if client.get('/login/', secure=True).status_code != 200:
    raise RuntimeError('Login page does not render from the deployment image.')
print('Packaged assets and login page are available in a fresh container.')
