from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.accounts"
    verbose_name = "Kullanıcılar ve Yetkiler"

    def ready(self) -> None:
        from apps.accounts import signals  # noqa: F401
