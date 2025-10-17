from django.apps import AppConfig


class BasketConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'basket'

    def ready(self):
        # import signals to connect handlers
        from . import signals  # noqa: F401
