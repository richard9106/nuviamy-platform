import json

from django.core.management.base import BaseCommand, CommandError

from apps.accounts.readiness import security_readiness_report


class Command(BaseCommand):
    help = 'Read-only security evidence, without secrets or patient records. Not HIPAA certification.'

    def add_arguments(self, parser):
        parser.add_argument('--fail-on-review', action='store_true',
                            help='Also fail when controls still require human evidence or review.')

    def handle(self, *args, **options):
        report = security_readiness_report()
        self.stdout.write(json.dumps(report, indent=2, sort_keys=True))
        if report['summary']['fail'] or (options['fail_on_review'] and report['summary']['review']):
            raise CommandError('Security readiness checks are incomplete; review the structured report.')
