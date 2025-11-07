from django.core.management.base import BaseCommand
from codingapp.models import sync_permissions


class Command(BaseCommand):
    help = "Recreate and assign all default permissions to roles"

    def handle(self, *args, **options):
        self.stdout.write("🚀 Resetting and syncing all permissions...")
        sync_permissions()
        self.stdout.write(self.style.SUCCESS("🎉 Permissions reset and reassigned successfully!"))
