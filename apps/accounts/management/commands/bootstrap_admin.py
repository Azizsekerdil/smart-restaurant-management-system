"""Create the one-time local bootstrap administrator on a fresh install."""

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.accounts.permissions import Role


class Command(BaseCommand):
    help = "Create admin/admin once on an empty installation."

    def handle(self, *args, **options):
        if User.objects.exists():
            self.stdout.write(self.style.WARNING("A user already exists; bootstrap skipped."))
            return
        user = User.objects.create_superuser(
            username="admin",
            password="admin",
            role=Role.OWNER,
            must_change_password=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Bootstrap account created: {user.username}. "
                "Sign in locally and change the password immediately."
            )
        )
