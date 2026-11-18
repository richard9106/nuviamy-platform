import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.practices.founding_offer import issue_founding_offer


class Command(BaseCommand):
    help = 'Issue one of fifty personal six-month codes. Private output; sends no email.'

    def add_arguments(self, parser):
        parser.add_argument('email')
        parser.add_argument('--rotate', action='store_true', help='Explicitly replace an unused code for the same email.')

    def handle(self, *args, **options):
        try:
            result = issue_founding_offer(options['email'], rotate=options['rotate'])
        except ValidationError as error:
            raise CommandError(error.messages[0]) from error
        self.stdout.write(json.dumps(result))
