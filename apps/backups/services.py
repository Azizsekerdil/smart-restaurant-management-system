"""Yedekleme ve geri yükleme işlemleri.

Tasarım kararları
-----------------
**Tutarlılık.** SQLite dosyasını çalışırken kopyalamak güvenli değildir:
WAL dosyasında henüz aktarılmamış işlemler olabilir ve kopya yarım bir
duruma denk gelebilir. Bunun yerine SQLite'ın kendi yedekleme API'si
(``Connection.backup``) kullanılır; motor kilitleri kendisi yönetir ve
tutarlı bir anlık görüntü üretir. PostgreSQL'de ``pg_dump`` tercih edilir,
bulunamazsa taşınabilir JSON dökümüne düşülür.

**Taşınabilirlik.** Arşive her zaman bir de ``veri.json`` (Django
``dumpdata``) konur. Ham veritabanı dosyası aynı motor sürümüne bağlıdır;
JSON dökümü ise PostgreSQL'e geçişte veya farklı bir kurulumda okunabilir.

**Gizlilik.** ``.env`` dosyası varsayılan olarak yedeğe **girmez**. Yedek
arşivi çoğu zaman e-postayla veya bulutla taşınır; API anahtarlarının bu
yolla sızması gerçek bir risktir. Kullanıcı açıkça isterse eklenir ve
kayıtta işaretlenir.

**Geri yükleme.** Yıkıcıdır. Bu yüzden önce mevcut durumun güvenlik yedeği
alınır, arşiv doğrulanır ve ancak ondan sonra dosyalar değiştirilir.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import sqlite3
import subprocess  # nosec B404  # noqa: S404
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connection, connections
from django.utils import timezone

from apps.backups.models import BackupRecord, RestoreRecord
from apps.core.models import AuditLog
from apps.core.services import record_audit

logger = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
DB_SQLITE_NAME = "veritabani.sqlite3"
DB_POSTGRES_NAME = "veritabani.dump"
JSON_DUMP_NAME = "veri.json"
MEDIA_DIR_NAME = "media"
ENV_NAME = "ayarlar.env"

#: Taşınabilir JSON dökümünden dışlanan uygulamalar. Bunlar kurulumla
#: birlikte yeniden üretilir; taşınmaları çakışma yaratır.
JSON_EXCLUDES = (
    "contenttypes",
    "auth.Permission",
    "sessions",
    "admin.logentry",
    "axes",
)


class BackupError(Exception):
    """Yedekleme veya geri yükleme başarısız oldu."""


@dataclass
class BackupResult:
    record: BackupRecord
    path: Path
    warnings: list[str] = field(default_factory=list)


# ==================================================================
#  Yardımcılar
# ==================================================================
def _timestamp() -> str:
    return timezone.localtime().strftime("%Y%m%d-%H%M%S")


def _unique_filename(suffix: str) -> str:
    """Çakışmayan bir dosya adı üretir.

    Aynı saniye içinde iki yedek alınabilir (örneğin geri yükleme öncesi
    güvenlik yedeği hemen ardından). Zaman damgası tek başına yeterli
    değildir; hem diskteki dosyaya hem de kayda bakılır.
    """
    stamp = _timestamp()
    base = f"yedek-{stamp}-{suffix}"
    candidate = f"{base}.zip"
    counter = 2
    while (Path(settings.BACKUP_DIR) / candidate).exists() or BackupRecord.objects.filter(
        filename=candidate
    ).exists():
        candidate = f"{base}-{counter}.zip"
        counter += 1
    return candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _db_settings() -> dict:
    return settings.DATABASES["default"]


def is_sqlite() -> bool:
    return "sqlite" in _db_settings()["ENGINE"]


def _dir_size(path: Path) -> int:
    total = 0
    for item in path.rglob("*"):
        if item.is_file():
            try:
                total += item.stat().st_size
            except OSError:  # pragma: no cover - erişim hatası
                continue
    return total


# ==================================================================
#  Veritabanı anlık görüntüsü
# ==================================================================
#: SQLite yedekleme adımı bir seferde kaç sayfa kopyalasın. Küçük parçalar
#: hâlinde ilerlemek, uzun süren kopyalamanın diğer isteklerin veritabanına
#: erişimini bloke etmesini önler.
_BACKUP_PAGES = 256

#: Kopyalama bu süreyi aşarsa vazgeçilir (saniye).
_BACKUP_TIMEOUT = 300


def _copy_sqlite(source: sqlite3.Connection, destination: sqlite3.Connection) -> None:
    """SQLite yedekleme API'siyle kopyalar, süresiz beklemeyi engeller.

    Python'un ``Connection.backup`` çağrısı, kaynak veritabanı kilitliyse
    SQLITE_BUSY alır ve **süresiz** yeniden dener. Çağıran kod bir
    ``transaction.atomic`` bloğunun içindeyse kilit hiç açılmaz ve uygulama
    tamamen donar. İlerleme geri çağrısı her denemede çalıştığı için, süre
    sınırını oradan uygularız.
    """
    import time

    deadline = time.monotonic() + _BACKUP_TIMEOUT

    def progress(status, remaining, total):  # noqa: ARG001 - API imzası
        if time.monotonic() > deadline:
            raise BackupError(
                "Veritabanı kopyalanamadı: veritabanı sürekli meşgul. "
                "Açık bir işlem (transaction) kopyalamayı engelliyor olabilir."
            )

    source.backup(destination, pages=_BACKUP_PAGES, progress=progress)


def _sqlite_path() -> Path | None:
    """Veritabanı gerçek bir dosyaysa yolunu döndürür.

    Bellek içi veritabanında (testlerin bir kısmı) dosya yoktur; o durumda
    Django'nun kendi bağlantısı üzerinden gitmek zorundayız.
    """
    name = str(_db_settings()["NAME"])
    if not name or name == ":memory:" or "mode=memory" in name:
        return None
    return Path(name)


def _snapshot_sqlite(target: Path) -> None:
    """SQLite veritabanının tutarlı bir kopyasını üretir.

    Dosyayı doğrudan kopyalamak güvenli değildir: WAL dosyasında henüz
    aktarılmamış işlemler olabilir ve kopya yarım bir duruma denk gelebilir.
    Motorun yedekleme API'si kilitleri kendisi yönetir.

    Kaynak için **ayrı bir salt okunur bağlantı** açılır. Django'nun
    bağlantısını kullanmak, çağıran kodun açık işlemiyle kilitlenmeye yol
    açardı. Yedeğe yalnızca işlenmiş (commit edilmiş) veri girer — zaten
    doğru davranış budur.
    """
    source_path = _sqlite_path()
    destination = sqlite3.connect(str(target))
    try:
        if source_path is None:
            connection.ensure_connection()
            _copy_sqlite(connection.connection, destination)
        else:
            source = sqlite3.connect(f"file:{source_path}?mode=ro", uri=True, timeout=30)
            try:
                _copy_sqlite(source, destination)
            finally:
                source.close()
    finally:
        destination.close()

    if not target.is_file() or target.stat().st_size == 0:
        raise BackupError(f"Veritabanı kopyası oluşturulamadı: {source_path or 'bellek'}")


def _snapshot_postgres(target: Path) -> str:
    """PostgreSQL mantıksal dökümü alır. Kullanılan yöntemi döndürür."""
    config = _db_settings()
    env = os.environ.copy()
    if config.get("PASSWORD"):
        env["PGPASSWORD"] = config["PASSWORD"]

    command = [
        "pg_dump",
        "-h",
        str(config.get("HOST") or "localhost"),
        "-p",
        str(config.get("PORT") or 5432),
        "-U",
        str(config.get("USER") or ""),
        "-d",
        str(config.get("NAME") or ""),
        "-F",
        "c",
        "-f",
        str(target),
    ]
    try:
        result = subprocess.run(  # nosec B603  # noqa: S603
            command,
            env=env,
            capture_output=True,
            timeout=1800,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise BackupError(
            "pg_dump çalıştırılamadı. PostgreSQL istemci araçlarının kurulu ve "
            f"PATH üzerinde olduğundan emin olun. Ayrıntı: {exc}"
        ) from exc

    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", "replace")[:500]
        raise BackupError(f"pg_dump başarısız (kod {result.returncode}): {detail}")
    return "pg_dump"


def _dump_json(target: Path) -> None:
    """Taşınabilir JSON dökümü."""
    with target.open("w", encoding="utf-8") as handle:
        call_command(
            "dumpdata",
            *[f"--exclude={item}" for item in JSON_EXCLUDES],
            natural_foreign=True,
            natural_primary=True,
            indent=2,
            stdout=handle,
            verbosity=0,
        )


# ==================================================================
#  Yedek oluşturma
# ==================================================================
def create_backup(
    *,
    user=None,
    kind: str = BackupRecord.Kind.MANUAL,
    include_media: bool = True,
    include_secrets: bool = False,
    note: str = "",
    request=None,
) -> BackupResult:
    """Veritabanı + medya + yapılandırmayı tek bir ZIP arşivine alır."""
    if include_secrets and not settings.BACKUP["ALLOW_SECRETS"]:
        # Ayar kapalıyken arayüzden gelen istek sessizce yok sayılmaz;
        # kullanıcı neyin olmadığını bilmelidir.
        raise BackupError(
            "Gizli ayarların yedeğe eklenmesi kapalı. Açmak için "
            "BACKUP_ALLOW_SECRETS=True yapın."
        )

    Path(settings.BACKUP_DIR).mkdir(parents=True, exist_ok=True)
    suffix = {"scheduled": "oto", "pre_restore": "guvenlik"}.get(kind, "elle")
    filename = _unique_filename(suffix)
    archive_path = Path(settings.BACKUP_DIR) / filename

    record = BackupRecord.objects.create(
        filename=filename,
        kind=kind,
        status=BackupRecord.Status.RUNNING,
        note=note[:300],
        created_by=user,
    )

    warnings: list[str] = []
    contents: dict = {}

    try:
        with tempfile.TemporaryDirectory(prefix="restaurant-backup-") as tmp:
            stage = Path(tmp)

            # ---------- veritabanı ----------
            if is_sqlite():
                _snapshot_sqlite(stage / DB_SQLITE_NAME)
                contents["veritabani"] = {
                    "motor": "sqlite",
                    "dosya": DB_SQLITE_NAME,
                    "bayt": (stage / DB_SQLITE_NAME).stat().st_size,
                }
            else:
                method = _snapshot_postgres(stage / DB_POSTGRES_NAME)
                contents["veritabani"] = {
                    "motor": "postgresql",
                    "dosya": DB_POSTGRES_NAME,
                    "yontem": method,
                    "bayt": (stage / DB_POSTGRES_NAME).stat().st_size,
                }

            # ---------- taşınabilir döküm ----------
            try:
                _dump_json(stage / JSON_DUMP_NAME)
                contents["json_dokum"] = {
                    "dosya": JSON_DUMP_NAME,
                    "bayt": (stage / JSON_DUMP_NAME).stat().st_size,
                }
            except Exception as exc:  # pragma: no cover - beklenmeyen model hatası
                # JSON dökümü olmasa da ham veritabanı yedeği geçerlidir.
                warnings.append(f"Taşınabilir JSON dökümü alınamadı: {exc}")
                logger.warning("JSON dökümü başarısız", exc_info=True)

            # ---------- medya ----------
            media_root = Path(settings.MEDIA_ROOT)
            if include_media and media_root.is_dir():
                size = _dir_size(media_root)
                limit = settings.BACKUP["MEDIA_LIMIT_MB"] * 1024 * 1024
                if limit and size > limit:
                    warnings.append(
                        f"Medya klasörü {round(size / 1024 / 1024)} MB — "
                        f"{settings.BACKUP['MEDIA_LIMIT_MB']} MB sınırını aştığı için "
                        "yedeğe eklenmedi."
                    )
                elif size:
                    shutil.copytree(media_root, stage / MEDIA_DIR_NAME)
                    file_count = sum(1 for p in media_root.rglob("*") if p.is_file())
                    contents["medya"] = {"dosya_sayisi": file_count, "bayt": size}

            # ---------- yapılandırma ----------
            env_file = Path(settings.DATA_DIR) / ".env"
            if include_secrets and env_file.is_file():
                shutil.copyfile(env_file, stage / ENV_NAME)
                contents["gizli_ayarlar"] = True
            elif env_file.is_file():
                warnings.append("Ayar dosyası (.env) yedeğe eklenmedi — API anahtarları içerir.")

            # ---------- manifest ----------
            manifest = {
                "surum": 1,
                "uygulama": "Akıllı Restaurant Yönetim Sistemi",
                "olusturulma": timezone.localtime().isoformat(),
                "olusturan": getattr(user, "username", "sistem"),
                "tur": kind,
                "django": _django_version(),
                "veritabani_motoru": "sqlite" if is_sqlite() else "postgresql",
                "icerik": contents,
                "uyarilar": warnings,
                "not": note,
            }
            (stage / MANIFEST_NAME).write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # ---------- arşivle ----------
            _write_archive(stage, archive_path)

        record.size_bytes = archive_path.stat().st_size
        record.checksum = _sha256(archive_path)
        record.contents = contents
        record.includes_secrets = bool(contents.get("gizli_ayarlar"))
        record.status = BackupRecord.Status.SUCCESS
        record.finished_at = timezone.now()
        record.save()

    except Exception as exc:
        record.status = BackupRecord.Status.FAILED
        record.error_message = str(exc)[:2000]
        record.finished_at = timezone.now()
        record.save()
        archive_path.unlink(missing_ok=True)
        logger.exception("Yedekleme başarısız")
        record_audit(
            AuditLog.Action.EXPORT,
            user=user,
            obj=record,
            description=f"Yedekleme başarısız: {exc}",
            severity=AuditLog.Severity.WARNING,
            request=request,
        )
        raise BackupError(str(exc)) from exc

    record_audit(
        AuditLog.Action.EXPORT,
        user=user,
        obj=record,
        description=(
            f"Yedek alındı: {filename} ({record.size_mb} MB, {record.get_kind_display()})"
        ),
        changes={"icerik": contents, "gizli_ayarlar": record.includes_secrets},
        severity=AuditLog.Severity.NOTICE,
        request=request,
    )

    apply_retention()
    return BackupResult(record=record, path=archive_path, warnings=warnings)


def _write_archive(stage: Path, archive_path: Path) -> None:
    """Hazırlık klasörünü ZIP'e yazar."""
    with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for item in sorted(stage.rglob("*")):
            if item.is_file():
                archive.write(item, item.relative_to(stage).as_posix())


def _django_version() -> str:
    import django

    return django.get_version()


# ==================================================================
#  Saklama politikası
# ==================================================================
def apply_retention() -> int:
    """Eski yedekleri siler, silinen sayısını döndürür.

    Güvenlik yedekleri (geri yükleme öncesi) korunur; onlar bir kazadan
    dönüş noktasıdır ve sayı sınırına takılmamalıdır.
    """
    keep = settings.BACKUP["KEEP_LAST"]
    if keep <= 0:
        return 0

    stale = list(
        BackupRecord.objects.filter(
            status=BackupRecord.Status.SUCCESS,
            kind__in=[BackupRecord.Kind.MANUAL, BackupRecord.Kind.SCHEDULED],
        ).order_by("-started_at")[keep:]
    )

    removed = 0
    for record in stale:
        try:
            record.path.unlink(missing_ok=True)
        except OSError:  # pragma: no cover - kilitli dosya
            logger.warning("Eski yedek silinemedi: %s", record.filename)
            continue
        record.delete()
        removed += 1
    return removed


# ==================================================================
#  Doğrulama
# ==================================================================
def inspect_archive(path: Path) -> dict:
    """Arşivi açmadan içeriğini ve manifestini okur."""
    if not path.is_file():
        raise BackupError(f"Yedek dosyası bulunamadı: {path.name}")

    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if MANIFEST_NAME not in names:
                raise BackupError("Bu dosya bu uygulamanın yedeği değil (manifest bulunamadı).")
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    except zipfile.BadZipFile as exc:
        raise BackupError("Yedek dosyası bozuk veya ZIP değil.") from exc
    except json.JSONDecodeError as exc:
        raise BackupError("Yedek manifesti okunamadı.") from exc

    manifest["_dosyalar"] = sorted(names)
    manifest["_veritabani_var"] = (
        bool({DB_SQLITE_NAME, DB_POSTGRES_NAME} & names) or JSON_DUMP_NAME in names
    )
    return manifest


def verify_checksum(record: BackupRecord) -> bool:
    """Kayıttaki sağlama toplamı dosyayla uyuşuyor mu?"""
    if not record.checksum or not record.exists:
        return False
    return _sha256(record.path) == record.checksum


# ==================================================================
#  Geri yükleme sonrası tutarlılık
# ==================================================================
def sync_records_from_disk() -> int:
    """Diskteki yedek dosyaları için eksik kayıtları oluşturur.

    İki durumda gerekir:

    1. **Geri yüklemeden sonra.** Geri yükleme veritabanının tamamını
       değiştirir; yedek kayıtları da arşivin çekildiği ana döner. Güvenlik
       yedeği diskte durur ama kaydı olmadığı için arayüzde görünmez —
       yani kullanıcı yanlış bir geri yüklemeden geri dönemez. Bu, sessiz
       ve tehlikeli bir veri kaybı yoludur.
    2. Yedek klasörü elle taşındığında veya dosyalar başka bir kurulumdan
       kopyalandığında.

    Oluşturulan kayıt sayısını döndürür.
    """
    backup_dir = Path(settings.BACKUP_DIR)
    if not backup_dir.is_dir():
        return 0

    known = set(BackupRecord.objects.values_list("filename", flat=True))
    created = 0

    for path in sorted(backup_dir.glob("*.zip")):
        if path.name in known:
            continue
        try:
            manifest = inspect_archive(path)
        except BackupError:
            # Bu klasördeki her ZIP bizim yedeğimiz olmak zorunda değil.
            continue

        started = _parse_manifest_time(manifest.get("olusturulma"))
        BackupRecord.objects.create(
            filename=path.name,
            kind=_normalize_kind(manifest.get("tur")),
            status=BackupRecord.Status.SUCCESS,
            size_bytes=path.stat().st_size,
            checksum=_sha256(path),
            started_at=started,
            finished_at=started,
            contents=manifest.get("icerik") or {},
            includes_secrets=bool((manifest.get("icerik") or {}).get("gizli_ayarlar")),
            note=(manifest.get("not") or "")[:300],
        )
        created += 1

    return created


def _parse_manifest_time(value) -> datetime:
    from django.utils.dateparse import parse_datetime

    if isinstance(value, str):
        parsed = parse_datetime(value)
        if parsed is not None:
            return parsed
    return timezone.now()


def _normalize_kind(value) -> str:
    valid = {choice.value for choice in BackupRecord.Kind}
    return value if value in valid else BackupRecord.Kind.MANUAL


def _user_still_exists(user) -> bool:
    """Kullanıcı geri yüklenen veritabanında hâlâ var mı?

    Geri yüklemeden sonra işlemi yapan kullanıcı, arşivin alındığı anda
    henüz oluşturulmamış olabilir. Ona referans veren bir kayıt yazmak
    yabancı anahtar hatası verir.
    """
    if user is None or getattr(user, "pk", None) is None:
        return False
    try:
        return type(user).objects.filter(pk=user.pk).exists()
    except Exception:  # pragma: no cover - tablo yoksa
        return False


# ==================================================================
#  Geri yükleme
# ==================================================================
def restore_backup(record: BackupRecord, *, user=None, request=None) -> RestoreRecord:
    """Yedeği geri yükler.

    Sıra önemlidir: önce arşiv doğrulanır, sonra mevcut durumun güvenlik
    yedeği alınır, en son dosyalar değiştirilir. Böylece doğrulama
    aşamasında çıkan bir hata mevcut veriye dokunmamış olur.
    """
    if not record.exists:
        raise BackupError("Yedek dosyası diskte bulunamadı.")

    manifest = inspect_archive(record.path)
    if not manifest.get("_veritabani_var"):
        raise BackupError("Yedekte veritabanı bulunmuyor; geri yükleme yapılamaz.")

    if record.checksum and not verify_checksum(record):
        raise BackupError("Yedek dosyasının sağlama toplamı uyuşmuyor; dosya bozulmuş olabilir.")

    engine = manifest.get("veritabani_motoru")
    current = "sqlite" if is_sqlite() else "postgresql"
    if engine != current:
        raise BackupError(
            f"Yedek {engine} veritabanından alınmış, sistem şu anda {current} "
            "kullanıyor. Farklı motorlar arasında ham geri yükleme yapılamaz; "
            "arşivdeki veri.json dosyasını loaddata ile içe aktarın."
        )

    # ---------- güvenlik yedeği ----------
    safety: BackupRecord | None = None
    try:
        safety = create_backup(
            user=user,
            kind=BackupRecord.Kind.PRE_RESTORE,
            include_media=True,
            include_secrets=False,
            note=f"{record.filename} geri yüklenmeden önce alındı",
            request=request,
        ).record
    except BackupError as exc:
        raise BackupError(
            f"Geri yükleme öncesi güvenlik yedeği alınamadı, işlem iptal edildi: {exc}"
        ) from exc

    # Kayıtlar geri yüklemeden SONRA yazılır. Geri yükleme veritabanının
    # tamamını değiştirdiği için, önce yazılan bir satır zaten silinirdi.
    source_filename = record.filename
    safety_filename = safety.filename if safety else ""
    username = getattr(user, "username", "") or "sistem"

    try:
        with tempfile.TemporaryDirectory(prefix="restaurant-restore-") as tmp:
            stage = Path(tmp)
            with zipfile.ZipFile(record.path) as archive:
                _safe_extract(archive, stage)

            if is_sqlite():
                _restore_sqlite(stage / DB_SQLITE_NAME)
            else:
                _restore_postgres(stage / DB_POSTGRES_NAME)

            media_source = stage / MEDIA_DIR_NAME
            if media_source.is_dir():
                _restore_media(media_source)

    except Exception as exc:
        logger.exception("Geri yükleme başarısız")
        RestoreRecord.objects.create(
            source_filename=source_filename,
            safety_backup=safety if _record_exists(safety) else None,
            performed_by_username=username,
            created_by=user if _user_still_exists(user) else None,
            status=RestoreRecord.Status.FAILED,
            error_message=str(exc)[:2000],
        )
        record_audit(
            AuditLog.Action.UPDATE,
            user=user if _user_still_exists(user) else None,
            description=(
                f"Geri yükleme BAŞARISIZ ({username}): {source_filename}. Hata: {exc}. "
                f"Güvenlik yedeği: {safety_filename or 'yok'}"
            ),
            severity=AuditLog.Severity.CRITICAL,
            request=request,
        )
        raise BackupError(str(exc)) from exc

    # Yedek kayıtları da arşivin alındığı ana döndü: diskteki dosyalar için
    # eksik kayıtları yeniden oluştur. Aksi halde güvenlik yedeği arayüzde
    # görünmez ve yanlış bir geri yüklemeden dönüş yolu kapanır.
    sync_records_from_disk()
    restored_safety = (
        BackupRecord.objects.filter(filename=safety_filename).first() if safety_filename else None
    )

    restore = RestoreRecord.objects.create(
        source_filename=source_filename,
        safety_backup=restored_safety,
        performed_by_username=username,
        created_by=user if _user_still_exists(user) else None,
        status=RestoreRecord.Status.SUCCESS,
    )

    record_audit(
        AuditLog.Action.UPDATE,
        user=user if _user_still_exists(user) else None,
        obj=restore,
        description=(
            f"Veriler {source_filename} yedeğinden geri yüklendi ({username}). "
            f"Güvenlik yedeği: {safety_filename or 'yok'}"
        ),
        changes={"kaynak": source_filename, "manifest": manifest.get("olusturulma")},
        severity=AuditLog.Severity.CRITICAL,
        request=request,
    )
    return restore


def _record_exists(record: BackupRecord | None) -> bool:
    if record is None or record.pk is None:
        return False
    return BackupRecord.objects.filter(pk=record.pk).exists()


def _safe_extract(archive: zipfile.ZipFile, destination: Path) -> None:
    """ZIP'i hedef klasörün dışına çıkmadan açar.

    Kötü niyetle hazırlanmış bir arşiv ``../..`` içeren yollarla sistemin
    başka yerlerine dosya yazdırabilir (zip slip). Her girdinin hedefi
    açıkça denetlenir.
    """
    destination = destination.resolve()
    for member in archive.infolist():
        target = (destination / member.filename).resolve()
        if not target.is_relative_to(destination):
            raise BackupError(
                f"Yedek güvenli değil: arşiv, klasör dışına dosya yazmaya çalışıyor "
                f"({member.filename})."
            )
    archive.extractall(destination)  # noqa: S202 - yollar yukarıda doğrulandı


def _restore_sqlite(source: Path) -> None:
    """SQLite veritabanının içeriğini yedekten geri yazar.

    Dosyayı değiştirmek yerine motorun yedekleme API'si ters yönde
    kullanılır: açık bağlantılar geçersizleşmez ve WAL dosyaları tutarlı
    kalır.
    """
    if not source.is_file():
        raise BackupError("Yedekte SQLite veritabanı dosyası yok.")

    # Yedeğin gerçekten okunabilir bir SQLite dosyası olduğunu önce doğrula.
    probe = sqlite3.connect(f"file:{source}?mode=ro", uri=True)
    try:
        probe.execute("SELECT count(*) FROM sqlite_master").fetchone()
    except sqlite3.DatabaseError as exc:
        probe.close()
        raise BackupError(f"Yedekteki veritabanı okunamıyor: {exc}") from exc

    # Açık bağlantılar kapatılır; aksi halde hem yazma kilidi çıkar hem de
    # geri yüklemeden sonra eski veriyi önbellekten okumaya devam ederler.
    connections.close_all()
    target_path = _sqlite_path()
    try:
        if target_path is None:
            connection.ensure_connection()
            _copy_sqlite(probe, connection.connection)
        else:
            destination = sqlite3.connect(str(target_path), timeout=30)
            try:
                _copy_sqlite(probe, destination)
            finally:
                destination.close()
    finally:
        probe.close()
    connections.close_all()


def _restore_postgres(source: Path) -> None:
    if not source.is_file():
        raise BackupError("Yedekte PostgreSQL dökümü yok.")

    config = _db_settings()
    env = os.environ.copy()
    if config.get("PASSWORD"):
        env["PGPASSWORD"] = config["PASSWORD"]

    connections.close_all()
    command = [
        "pg_restore",
        "--clean",
        "--if-exists",
        "--no-owner",
        "-h",
        str(config.get("HOST") or "localhost"),
        "-p",
        str(config.get("PORT") or 5432),
        "-U",
        str(config.get("USER") or ""),
        "-d",
        str(config.get("NAME") or ""),
        str(source),
    ]
    try:
        result = subprocess.run(  # nosec B603  # noqa: S603
            command, env=env, capture_output=True, timeout=3600, check=False
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        raise BackupError(f"pg_restore çalıştırılamadı: {exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or b"").decode("utf-8", "replace")[:500]
        raise BackupError(f"pg_restore başarısız (kod {result.returncode}): {detail}")


def _restore_media(source: Path) -> None:
    """Medya dosyalarını geri yazar.

    Mevcut klasör silinmez, üzerine yazılır: yedekten sonra yüklenmiş
    dosyaların sessizce kaybolması, çoğu durumda geri yüklemenin
    beklenmeyen bir yan etkisidir.
    """
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, media_root, dirs_exist_ok=True)


# ==================================================================
#  Özet
# ==================================================================
def storage_summary() -> dict:
    """Yedek klasörünün durumu (arayüzde gösterilir)."""
    records = BackupRecord.objects.filter(status=BackupRecord.Status.SUCCESS)
    total_bytes = sum(r.size_bytes for r in records)
    last = records.order_by("-started_at").first()

    free_bytes = None
    try:
        free_bytes = shutil.disk_usage(settings.BACKUP_DIR).free
    except OSError:  # pragma: no cover - erişilemeyen sürücü
        pass

    return {
        "klasor": str(settings.BACKUP_DIR),
        "adet": records.count(),
        "toplam_mb": round(total_bytes / (1024 * 1024), 1),
        "bos_alan_gb": round(free_bytes / (1024**3), 1) if free_bytes else None,
        "son_yedek": last,
        "saklanan": settings.BACKUP["KEEP_LAST"],
        "otomatik": settings.BACKUP["SCHEDULE_ENABLED"],
        "otomatik_saat": settings.BACKUP["SCHEDULE_HOURS"],
        "gizli_ayarlara_izin": settings.BACKUP["ALLOW_SECRETS"],
    }


def last_successful_backup() -> BackupRecord | None:
    return (
        BackupRecord.objects.filter(status=BackupRecord.Status.SUCCESS)
        .order_by("-started_at")
        .first()
    )


def hours_since_last_backup() -> float | None:
    last = last_successful_backup()
    if last is None:
        return None
    delta: datetime = timezone.now() - last.started_at
    return delta.total_seconds() / 3600
