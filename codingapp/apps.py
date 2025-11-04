from django.apps import AppConfig

from django.apps import AppConfig

class CodingappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "codingapp"

    def ready(self):
        from .models import ensure_default_permissions, assign_default_permissions_to_roles
        ensure_default_permissions()
        assign_default_permissions_to_roles()
