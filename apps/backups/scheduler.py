"""Otomatik yedekleme zamanlayıcısı.

Neden Celery değil
------------------
Projede Celery isteğe bağlıdır ve paketlenmiş masaüstü sürümünde hiç
çalışmaz (Redis kurulumu gerektirir). Tek restoranlık bir kurulumda günde
bir kez yedek almak için ayrı bir altyapı taşımak gereksizdir; bu yüzden
sunucu sürecinin içinde çalışan hafif bir arka plan iş parçacığı yeterli
görülmüştür.

Ölçek büyüdüğünde (çok sunuculu kurulum) bu zamanlayıcı kapatılıp
``python manage.py backup_now`` komutu Görev Zamanlayıcı / cron ile
çağrılmalıdır — aynı kod yolunu kullanır.

Birden çok sunucu süreci varsa her biri kendi zamanlayıcısını başlatır.
Bunu önlemek için yedekler arası asgari süre veritabanındaki son yedeğe
bakılarak denetlenir; aynı anda iki yedek alınmaz.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

from django.conf import settings

logger = logging.getLogger(__name__)

#: Zamanlayıcının uyanma sıklığı. Saat başı uyanıp "vakit geldi mi" diye
#: bakmak, uzun uykudan sonra saatin kaymasına karşı daha dayanıklıdır.
_TICK_SECONDS = 900

_thread: threading.Thread | None = None
_lock = threading.Lock()


def _should_start() -> bool:
    """Zamanlayıcı bu süreçte başlatılmalı mı?"""
    if not settings.BACKUP["SCHEDULE_ENABLED"]:
        return False

    # Test, migration ve tek seferlik yönetim komutlarında çalışmamalı.
    if getattr(settings, "IS_TEST", False):
        return False
    argv = " ".join(sys.argv)
    for command in ("migrate", "makemigrations", "collectstatic", "test", "shell", "backup_now"):
        if command in argv:
            return False

    # runserver'ın yeniden yükleyici ana süreci uygulamayı iki kez kurar;
    # yalnızca gerçek çalışan süreçte başlat.
    if "runserver" in argv and os.environ.get("RUN_MAIN") != "true":
        return False
    return True


def start_if_enabled() -> bool:
    """Zamanlayıcıyı başlatır. Başlatıldıysa True döner."""
    global _thread

    if not _should_start():
        return False

    with _lock:
        if _thread is not None and _thread.is_alive():
            return False
        _thread = threading.Thread(
            target=_loop,
            name="backup-scheduler",
            daemon=True,  # sunucu kapanırken süreci bekletmesin
        )
        _thread.start()

    logger.info(
        "Otomatik yedekleme açık: her %s saatte bir",
        settings.BACKUP["SCHEDULE_HOURS"],
    )
    return True


def _loop() -> None:
    # İlk kontrolden önce kısa bir bekleme: uygulama açılışında veritabanı
    # hazır olmayabilir.
    time.sleep(30)
    while True:
        try:
            run_due_backup()
        except Exception:  # pragma: no cover - zamanlayıcı asla ölmemeli
            logger.exception("Otomatik yedekleme sırasında beklenmeyen hata")
        time.sleep(_TICK_SECONDS)


def run_due_backup() -> bool:
    """Vakti geldiyse yedek alır. Aldıysa True döner."""
    from apps.backups import services

    interval = settings.BACKUP["SCHEDULE_HOURS"]
    if interval <= 0:
        return False

    elapsed = services.hours_since_last_backup()
    if elapsed is not None and elapsed < interval:
        return False

    logger.info("Otomatik yedekleme başlıyor")
    try:
        result = services.create_backup(
            kind="scheduled",
            include_media=True,
            include_secrets=False,
            note="Zamanlanmış otomatik yedek",
        )
    except services.BackupError as exc:
        logger.error("Otomatik yedekleme başarısız: %s", exc)
        _notify_failure(str(exc))
        return False

    logger.info("Otomatik yedek alındı: %s (%s MB)", result.record.filename, result.record.size_mb)
    return True


def _notify_failure(message: str) -> None:
    """Yöneticilere bildirim bırakır.

    Otomatik yedeklemenin sessizce başarısız olması, felaket anında
    yedek olmadığının anlaşılması demektir; bu yüzden görünür bir iz
    bırakılır.
    """
    try:
        from django.urls import reverse

        from apps.core.models import Notification

        Notification.objects.create(
            title="Otomatik yedekleme başarısız",
            body=f"Yedek alınamadı: {message[:400]}",
            level=Notification.Level.DANGER,
            category=Notification.Category.SYSTEM,
            target_roles=["owner", "general_manager", "restaurant_manager"],
            url=reverse("backups:index"),
        )
    except Exception:  # pragma: no cover - bildirim ikincil
        logger.exception("Yedekleme hatası bildirimi oluşturulamadı")
