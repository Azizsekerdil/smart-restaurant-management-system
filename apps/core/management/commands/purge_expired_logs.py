"""Saklama süresi dolan kişisel veri alanlarını redakte eder (KVKK/GDPR).

Kayıtlar SİLİNMEZ; yalnızca kişisel veri içeren alanlar temizlenir. Böylece
denetim izi ve operasyonel istatistikler (sayılar, durumlar, zamanlar)
korunurken saklama sınırlaması (storage limitation) ilkesi uygulanır.

Süreler `RETENTION` ayarlarından okunur (gün; 0 = kapalı). Varsayılan tümü
kapalıdır: süre kararı işletme/veri sorumlusuna aittir, kod dayatmaz.

Kullanım:
    python manage.py purge_expired_logs            # önizleme (hiçbir şey değişmez)
    python manage.py purge_expired_logs --apply    # redaksiyonu uygular + kanıt kaydı

Kapsam:
    - AuditLog.ip_address / user_agent      (RETENTION_AUDIT_IP_DAYS)
    - ConsentRecord.ip_address              (RETENTION_CONSENT_IP_DAYS)
    - Rezervasyon misafir bilgileri         (RETENTION_RESERVATION_GUEST_DAYS)
    - Bekleme listesi misafir bilgileri     (RETENTION_WAITLIST_GUEST_DAYS)
"""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

ANONYMIZED_GUEST = "Anonim Misafir"


class Command(BaseCommand):
    help = "Saklama süresi dolan kişisel veri alanlarını redakte eder (önizleme varsayılan)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Redaksiyonu gerçekten uygula (bayrak yoksa yalnızca önizleme yapılır).",
        )

    def handle(self, *args, **options):
        apply_changes: bool = options["apply"]
        retention = settings.RETENTION
        now = timezone.now()
        results: list[tuple[str, int, int]] = []  # (etiket, gün, kayıt sayısı)

        results.append(self._purge_audit_ips(retention["AUDIT_IP_DAYS"], now, apply_changes))
        results.append(self._purge_consent_ips(retention["CONSENT_IP_DAYS"], now, apply_changes))
        results.append(
            self._purge_reservations(retention["RESERVATION_GUEST_DAYS"], now, apply_changes)
        )
        results.append(self._purge_waitlist(retention["WAITLIST_GUEST_DAYS"], now, apply_changes))

        mode = "UYGULANDI" if apply_changes else "ÖNİZLEME (değişiklik yapılmadı)"
        self.stdout.write(self.style.MIGRATE_HEADING(f"Saklama temizliği — {mode}"))
        touched_total = 0
        for label, days, count in results:
            if days <= 0:
                self.stdout.write(f"  {label}: KAPALI (süre tanımlanmadı)")
                continue
            touched_total += count
            self.stdout.write(f"  {label}: {days} günden eski {count} kayıt")

        if all(days <= 0 for _, days, _ in results):
            self.stdout.write(
                self.style.WARNING(
                    "Hiçbir saklama süresi tanımlı değil. .env içinde RETENTION_* "
                    "değişkenlerini işletme/DPO kararına göre ayarlayın."
                )
            )
            return

        if apply_changes:
            self._record_evidence(results, touched_total)
            self.stdout.write(self.style.SUCCESS(f"Toplam {touched_total} kayıt redakte edildi."))
        else:
            self.stdout.write("Uygulamak için: python manage.py purge_expired_logs --apply")

    # ------------------------------------------------------------------
    #  Kategoriler
    # ------------------------------------------------------------------
    def _purge_audit_ips(self, days: int, now, apply_changes: bool):
        from apps.core.models import AuditLog

        label = "AuditLog IP/user-agent"
        if days <= 0:
            return (label, days, 0)
        from django.db.models import Q

        cutoff = now - timedelta(days=days)
        qs = AuditLog.objects.filter(timestamp__lt=cutoff).filter(
            Q(ip_address__isnull=False) | ~Q(user_agent="")
        )
        count = qs.count()
        if apply_changes and count:
            # AuditLog.save() değişikliği engeller (append-only). Buradaki
            # queryset.update() kasıtlıdır: kayıt içeriği değil, yalnızca
            # saklama süresi dolan kişisel veri alanları boşaltılır ve işlem
            # ayrı bir denetim kaydıyla (aşağıda) kanıtlanır.
            qs.update(ip_address=None, user_agent="")
        return (label, days, count)

    def _purge_consent_ips(self, days: int, now, apply_changes: bool):
        from apps.crm.models import ConsentRecord

        label = "ConsentRecord IP"
        if days <= 0:
            return (label, days, 0)
        cutoff = now - timedelta(days=days)
        qs = ConsentRecord.objects.filter(created_at__lt=cutoff, ip_address__isnull=False)
        count = qs.count()
        if apply_changes and count:
            # Rıza kaydının kendisi (tür/karar/zaman/kanal) kanıt olarak
            # kalır; yalnızca IP redakte edilir.
            qs.update(ip_address=None)
        return (label, days, count)

    def _purge_reservations(self, days: int, now, apply_changes: bool):
        from apps.floor.models import Reservation

        label = "Rezervasyon misafir bilgileri"
        if days <= 0:
            return (label, days, 0)
        cutoff = now - timedelta(days=days)
        qs = Reservation.objects.filter(
            status__in=[
                Reservation.Status.COMPLETED,
                Reservation.Status.CANCELLED,
                Reservation.Status.NO_SHOW,
            ],
            updated_at__lt=cutoff,
        ).exclude(guest_name=ANONYMIZED_GUEST)
        count = qs.count()
        if apply_changes and count:
            qs.update(
                guest_name=ANONYMIZED_GUEST,
                guest_phone="",
                guest_email="",
                special_requests="",
                allergy_notes="",
                occasion="",
                cancellation_reason="",
            )
        return (label, days, count)

    def _purge_waitlist(self, days: int, now, apply_changes: bool):
        from apps.floor.models import WaitlistEntry

        label = "Bekleme listesi misafir bilgileri"
        if days <= 0:
            return (label, days, 0)
        cutoff = now - timedelta(days=days)
        qs = WaitlistEntry.objects.filter(
            status__in=[WaitlistEntry.Status.SEATED, WaitlistEntry.Status.LEFT],
            updated_at__lt=cutoff,
        ).exclude(guest_name=ANONYMIZED_GUEST)
        count = qs.count()
        if apply_changes and count:
            qs.update(guest_name=ANONYMIZED_GUEST, guest_phone="", note="")
        return (label, days, count)

    # ------------------------------------------------------------------
    #  Kanıt kaydı
    # ------------------------------------------------------------------
    def _record_evidence(self, results, touched_total: int) -> None:
        from apps.core.models import AuditLog
        from apps.core.services import record_audit

        summary = "; ".join(
            f"{label}: {count} kayıt ({days} gün)" for label, days, count in results if days > 0
        )
        record_audit(
            AuditLog.Action.DATA_ERASURE,
            user=None,
            description=(
                f"Saklama süresi temizliği (purge_expired_logs --apply): {summary}. "
                f"Toplam {touched_total} kayıt redakte edildi."
            ),
            severity=AuditLog.Severity.WARNING,
        )
