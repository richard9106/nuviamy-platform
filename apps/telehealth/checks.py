from django.conf import settings
from django.core.checks import Error, register


@register()
def video_configuration(app_configs, **kwargs):
    if not settings.TELEHEALTH_ENABLED:
        return []
    errors = []
    if not settings.TELEHEALTH_PRACTICE_IDS and not settings.TELEHEALTH_GENERAL_AVAILABLE:
        errors.append(Error('Embedded video requires explicit approved pilot practice IDs.', id='telehealth.E001'))
    if settings.TELEHEALTH_CONTROL_REGION not in {'us-east-1', 'eu-central-1'}:
        errors.append(Error('Choose a supported video control Region: us-east-1 or eu-central-1.', id='telehealth.E002'))
    if settings.TELEHEALTH_MEDIA_REGION not in {'us-east-1', 'us-west-2', 'eu-central-1', 'eu-west-1'}:
        errors.append(Error('Choose a reviewed video media Region.', id='telehealth.E003'))
    if settings.TELEHEALTH_GENERAL_AVAILABLE and (settings.TELEHEALTH_CONTROL_REGION,settings.TELEHEALTH_MEDIA_REGION)!=('us-east-1','us-east-1'):
        errors.append(Error('General video activation currently discloses us-east-1 only.',id='telehealth.E004'))
    return errors
