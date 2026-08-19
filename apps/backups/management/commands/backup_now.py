"""Komut satırından yedek alır.

Windows Görev Zamanlayıcı veya cron ile çağrılmak üzere tasarlanmıştır;
uygulama içindeki zamanlayıcıyla aynı kod yolunu kullanır.

    python manage.py backup_now
    python manage.py backup_now --no-media --note "surum yukseltme oncesi"
    python manage.py backup_now --if-due          # yalnızca vakti geldiyse
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.backups import services
from apps.backups.models import BackupRecord


class Command(BaseCommand):
    help = "Veritabanı, medya ve yapılandırmayı tek bir arşive yedekler."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-media",
            action="store_true",
            help="Medya klasörünü yedeğe dahil etme.",
        )
        parser.add_argument(
            "--with-secrets",
            action="store_true",
            help=".env dosyasını dahil et (API anahtarları içerir!).",
        )
        parser.add_argument("--note", default="", help="Yedeğe not ekle.")
        parser.add_argument(
            "--if-due",
            action="store_true",
            help="Yalnızca zamanlama aralığı dolduysa yedek al.",
        )

    def handle(self, *args, **options):
        if options["if_due"]:
            from apps.backups import scheduler

            if not scheduler.run_due_backup():
                self.stdout.write("Yedekleme zamanı gelmemiş, atlandı.")
                return
            self.stdout.write(self.style.SUCCESS("[OK] Zamanlanmış yedek alındı."))
            return

        self.stdout.write("Yedek alınıyor...")
        try:
            result = services.create_backup(
                kind=BackupRecord.Kind.MANUAL,
                include_media=not options["no_media"],
                include_secrets=options["with_secrets"],
                note=options["note"],
            )
        except services.BackupError as exc:
            raise CommandError(f"Yedekleme başarısız: {exc}") from exc

        for warning in result.warnings:
            self.stdout.write(self.style.WARNING(f"  [!] {warning}"))

        record = result.record
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"[OK] {record.filename}"))
        self.stdout.write(f"     Konum : {result.path}")
        self.stdout.write(f"     Boyut : {record.size_mb} MB")
        self.stdout.write(f"     Sure  : {record.duration_seconds} sn")
        if record.includes_secrets:
            self.stdout.write(self.style.WARNING("     UYARI : Arsiv API anahtarlarini iceriyor."))
