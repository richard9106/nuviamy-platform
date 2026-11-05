import json
from django.core.management.base import BaseCommand
from apps.telehealth.health import video_health


class Command(BaseCommand):
    help = 'Print only non-identifying embedded-video health flags for operational monitoring.'

    def handle(self, *args, **kwargs):
        self.stdout.write(json.dumps(video_health()))
