from django.apps import AppConfig

class TottimeappConfig(AppConfig):
    name = 'tottimeapp'

    def ready(self):
        import tottimeapp.signals  # Import signals here
