from django.apps import AppConfig

class CodingappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "codingapp"

    def ready(self):
        from .models import ensure_default_permissions
        ensure_default_permissions()
