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
                email.message()  # Retain Django's header validation.
                charset = email.encoding or settings.DEFAULT_CHARSET
                if email.content_subtype not in ('plain', 'html'):
                    raise ValueError('Unsupported transactional email content type.')
                body = {'Html' if email.content_subtype == 'html' else 'Text':
                        {'Data': email.body, 'Charset': charset}}
                for content, mimetype in getattr(email, 'alternatives', ()):
                    if mimetype not in ('text/plain', 'text/html'):
                        raise ValueError('Unsupported transactional email alternative.')
                    body['Html' if mimetype == 'text/html' else 'Text'] = {'Data': content, 'Charset': charset}
                destination = {key: values for key, values in (
                    ('ToAddresses', email.to), ('CcAddresses', email.cc), ('BccAddresses', email.bcc)) if values}
                # Simple content uses only ses:SendEmail. Raw MIME unexpectedly
                # requires SendRawEmail even through the SES v2 SendEmail API.
                client.send_email(FromEmailAddress=email.from_email,
                    Destination=destination,
                    Content={'Simple': {'Subject': {'Data': email.subject, 'Charset': charset}, 'Body': body}},
                    **({'ReplyToAddresses': email.reply_to} if email.reply_to else {}),
                    ConfigurationSetName=configuration)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    # Provider errors can include destinations/subject/body; no SMTP fallback.
                    raise RuntimeError('Transactional email delivery failed; review the private service status.') from None
        return sent
