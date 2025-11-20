from django.apps import AppConfig

from django.apps import AppConfig

class CodingappConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "codingapp"

    def ready(self):
        from .models import ensure_default_permissions, assign_default_permissions_to_roles
        ensure_default_permissions()
        assign_default_permissions_to_roles()
# codingapp/apps.py
from django.apps import AppConfig


class CodingAppConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "codingapp"

    def ready(self):
        """
        Safe initialization — no direct database access here.
        Permissions are handled via management command (`reset_permissions`).
        """
        # No direct DB queries or imports that access the ORM here.
        # If you add a signals.py file in the future, uncomment this:
        # from codingapp import signals
        pass
