from django.apps import AppConfig


class TicketsConfig(AppConfig):
    name = 'tickets'
    default_auto_field = 'django.db.models.BigAutoField'

    def ready(self):
        import tickets.signals

