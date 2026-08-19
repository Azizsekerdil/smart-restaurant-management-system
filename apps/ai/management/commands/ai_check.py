"""Yapay zekâ sağlayıcılarını komut satırından test eder.

Kullanım:
    python manage.py ai_check                 # tüm sağlayıcıları test et
    python manage.py ai_check --provider lmstudio
    python manage.py ai_check --ask "Merhaba, çalışıyor musun?"

API anahtarları hiçbir zaman ekrana yazılmaz.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.ai import gateway
from apps.ai.models import AITask


class Command(BaseCommand):
    help = "AI sağlayıcı bağlantılarını test eder ve model listesini gösterir."

    def add_arguments(self, parser):
        parser.add_argument(
            "--provider", type=str, default="", help="Yalnızca bu sağlayıcıyı test et"
        )
        parser.add_argument("--ask", type=str, default="", help="Test sorusu gönder")
        parser.add_argument("--timeout", type=int, default=30)

    def handle(self, *args, **options):
        provider_key = options["provider"]
        timeout = options["timeout"]

        self.stdout.write(self.style.MIGRATE_HEADING("AI sağlayıcı durumu"))
        self.stdout.write("")

        results = (
            [gateway.test_provider(provider_key, timeout=timeout)]
            if provider_key
            else gateway.test_all_providers(timeout=timeout)
        )

        for result in results:
            label = result.get("label", result["key"])
            if result["ok"]:
                self.stdout.write(
                    self.style.SUCCESS(f"  [OK]   {label:<24} {result['latency_ms']:>6} ms")
                )
                self.stdout.write(f"         {result['message']}")
                models = result.get("models") or []
                if models:
                    self.stdout.write(f"         Modeller ({len(models)}):")
                    for model in models[:15]:
                        self.stdout.write(f"           - {model}")
                configured = result.get("configured_models") or {}
                if configured:
                    self.stdout.write("         Görev eşlemesi:")
                    for task, model in configured.items():
                        # Windows konsolunun Türkçe kod sayfasında bulunmayan
                        # semboller kullanılmaz (bkz. seed_demo).
                        mark = "+" if (not models or model in models) else "!"
                        self.stdout.write(f"           {mark} {task:<12} -> {model}")
            else:
                self.stdout.write(self.style.ERROR(f"  [HATA] {label:<24}"))
                self.stdout.write(f"         {result['message']}")
            self.stdout.write("")

        budget = gateway.budget_status()
        self.stdout.write(self.style.MIGRATE_HEADING("Bütçe"))
        self.stdout.write(
            f"  Bugün: {budget['spent_today']:.4f} / {budget['daily_limit']} USD"
            f"   ·   Bu ay: {budget['spent_month']:.4f} / {budget['monthly_limit']} USD"
        )
        self.stdout.write("")

        if options["ask"]:
            self.stdout.write(self.style.MIGRATE_HEADING("Test sorusu"))
            self.stdout.write(f"  Soru: {options['ask']}")
            try:
                response = gateway.ask(
                    options["ask"],
                    system="Kısa ve net yanıt ver. En fazla 2 cümle.",
                    task=AITask.GENERAL,
                    feature="cli_check",
                    timeout=timeout * 8,
                )
                self.stdout.write(self.style.SUCCESS(f"  Yanıt: {response.text}"))
                self.stdout.write(
                    f"  Sağlayıcı: {response.provider} · Model: {response.model} · "
                    f"{response.latency_ms} ms · {response.total_tokens} token"
                )
            except gateway.AIUnavailable as exc:
                self.stdout.write(self.style.ERROR(f"  Başarısız: {exc}"))
