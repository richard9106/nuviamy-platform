from django.apps import AppConfig


class TelehealthConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.telehealth'

    def ready(self):
        from . import checks, signals  # noqa: F401
