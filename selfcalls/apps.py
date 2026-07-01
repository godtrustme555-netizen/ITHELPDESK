from django.apps import AppConfig


class SelfcallsConfig(AppConfig):
    name = 'selfcalls'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        import selfcalls.signals
