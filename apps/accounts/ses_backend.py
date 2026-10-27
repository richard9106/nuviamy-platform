"""Transactional SES mail using the instance role; no SMTP access keys or fallback."""
from email.utils import parseaddr

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend


class EmailBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        region = settings.AWS_SES_REGION
        configuration = settings.AWS_SES_CONFIGURATION_SET
        sender = parseaddr(settings.DEFAULT_FROM_EMAIL)[1]
        if not region or region == 'auto' or not configuration or not sender:
            raise ImproperlyConfigured('SES requires an explicit region, configuration set and sender.')
        sent = 0
        client = boto3.client('sesv2', region_name=region,
            config=Config(connect_timeout=5, read_timeout=15, retries={'max_attempts': 2}))
        for email in email_messages:
            if not email.recipients():
                continue
            try:
                if parseaddr(email.from_email)[1].casefold() != sender.casefold():
                    raise ValueError('SES sender must match the configured transactional identity.')
                if email.attachments:
                    raise ValueError('Transactional email does not support clinical document attachments.')
                client.send_email(FromEmailAddress=email.from_email,
                    Destination={'ToAddresses': email.recipients()},
                    Content={'Raw': {'Data': email.message().as_bytes(linesep='\r\n')}},
                    ConfigurationSetName=configuration)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    # Provider errors can include destinations/subject/body; no SMTP fallback.
                    raise RuntimeError('Transactional email delivery failed; review the private service status.') from None
        return sent
