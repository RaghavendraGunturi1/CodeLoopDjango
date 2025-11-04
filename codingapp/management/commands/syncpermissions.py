from django.core.management.base import BaseCommand
from codingapp.models import ensure_default_permissions, assign_default_permissions_to_roles
from django.db.utils import OperationalError, ProgrammingError

class Command(BaseCommand):
    help = "Syncs all default ActionPermissions and assigns them to roles (Admin, HOD, Teacher, Student)."

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("🔄 Syncing permissions..."))

        try:
            # Step 1: Ensure all defined permissions exist
            ensure_default_permissions()
            self.stdout.write(self.style.SUCCESS("✅ Default permissions verified."))

            # Step 2: Assign them to roles
            assign_default_permissions_to_roles()
            self.stdout.write(self.style.SUCCESS("✅ Role default permissions assigned."))

            self.stdout.write(self.style.SUCCESS("🎉 Permission sync completed successfully."))

        except (OperationalError, ProgrammingError):
            self.stdout.write(self.style.ERROR("❌ Database not ready. Run migrations first."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error: {e}"))
