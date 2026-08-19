from django.apps import AppConfig


class BackupsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.backups"
    verbose_name = "Yedekleme"

    def ready(self) -> None:
        # Zamanlayıcı yalnızca gerçek sunucu sürecinde başlar; migration,
        # test ve yönetim komutlarında başlatılmaz (bkz. scheduler.py).
        from apps.backups import scheduler

        scheduler.start_if_enabled()
