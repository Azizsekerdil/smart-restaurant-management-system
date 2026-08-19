"""Ortak yardımcılar: para birimi, yuvarlama, kod üretimi, dosya doğrulama."""

from __future__ import annotations

import secrets
import string
import unicodedata
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

MONEY = Decimal("0.01")
QTY = Decimal("0.001")


def money(value) -> Decimal:
    """Parasal değeri 2 haneye yuvarlar (yarım yukarı)."""
    if value is None:
        return Decimal("0.00")
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


def quantity(value) -> Decimal:
    """Miktarı 3 haneye yuvarlar (gram/ml hassasiyeti)."""
    if value is None:
        return Decimal("0.000")
    return Decimal(str(value)).quantize(QTY, rounding=ROUND_HALF_UP)


def percent_of(value, rate) -> Decimal:
    """value * rate / 100 (parasal yuvarlama ile)."""
    return money(Decimal(str(value)) * Decimal(str(rate)) / Decimal("100"))


def format_money(value) -> str:
    symbol = settings.RESTAURANT["CURRENCY_SYMBOL"]
    amount = money(value)
    # Türkçe biçim: 1.234,56 ₺
    whole, _sep, frac = f"{amount:.2f}".partition(".")
    negative = whole.startswith("-")
    whole = whole.lstrip("-")
    grouped = ""
    while len(whole) > 3:
        grouped = "." + whole[-3:] + grouped
        whole = whole[:-3]
    grouped = whole + grouped
    sign = "-" if negative else ""
    return f"{sign}{grouped},{frac} {symbol}"


def safe_divide(numerator, denominator, default=Decimal("0")) -> Decimal:
    try:
        d = Decimal(str(denominator))
        if d == 0:
            return Decimal(str(default))
        return Decimal(str(numerator)) / d
    except Exception:
        return Decimal(str(default))


def generate_code(prefix: str = "", length: int = 6) -> str:
    """Karışması zor (I/O/0/1 içermeyen) rastgele kod üretir."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    body = "".join(secrets.choice(alphabet) for _ in range(length))
    return f"{prefix}{body}" if prefix else body


def daily_sequence_number(model, field: str = "number", prefix: str = "") -> str:
    """Gün içinde artan belge numarası üretir: PREFIX-YYYYMMDD-0001."""
    today = timezone.localdate()
    stamp = today.strftime("%Y%m%d")
    base = f"{prefix}{stamp}-"
    last = (
        model.objects.filter(**{f"{field}__startswith": base})
        .order_by(f"-{field}")
        .values_list(field, flat=True)
        .first()
    )
    counter = 1
    if last:
        try:
            counter = int(str(last).rsplit("-", 1)[-1]) + 1
        except ValueError:
            counter = 1
    return f"{base}{counter:04d}"


def slugify_tr(text: str) -> str:
    """Türkçe karakterleri koruyarak URL uyumlu slug üretir."""
    mapping = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    text = (text or "").translate(mapping)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    out = []
    prev_dash = False
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
            prev_dash = False
        elif not prev_dash:
            out.append("-")
            prev_dash = True
    return "".join(out).strip("-") or "kayit"


def date_range(start: date, end: date):
    """start..end (dahil) arasındaki günleri üretir."""
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def period_bounds(period: str, reference: date | None = None) -> tuple[date, date]:
    """'today' | 'week' | 'month' | 'year' için başlangıç/bitiş tarihi."""
    ref = reference or timezone.localdate()
    if period == "week":
        start = ref - timedelta(days=ref.weekday())
        return start, ref
    if period == "month":
        return ref.replace(day=1), ref
    if period == "year":
        return ref.replace(month=1, day=1), ref
    return ref, ref


def start_of_day(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, datetime.min.time()))


def end_of_day(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, datetime.max.time()))


# ------------------------------------------------------------------
#  Güvenli dosya yükleme
# ------------------------------------------------------------------
_IMAGE_MAGIC = {
    b"\xff\xd8\xff": "image/jpeg",
    b"\x89PNG\r\n\x1a\n": "image/png",
    b"GIF87a": "image/gif",
    b"GIF89a": "image/gif",
    b"RIFF": "image/webp",
    b"%PDF": "application/pdf",
}


def validate_upload(uploaded_file) -> None:
    """Yüklenen dosyanın uzantısını, boyutunu ve gerçek türünü doğrular.

    Yalnızca uzantıya güvenmez; dosya imzasını (magic bytes) da kontrol
    eder. Bu, ".jpg" adıyla yüklenen çalıştırılabilir dosyaları engeller.
    """
    max_size = settings.FILE_UPLOAD_MAX_MEMORY_SIZE
    if uploaded_file.size > max_size:
        raise ValidationError(
            _("Dosya çok büyük (%(size)s MB). En fazla %(max)s MB yükleyebilirsiniz.")
            % {"size": round(uploaded_file.size / 1048576, 1), "max": max_size // 1048576}
        )

    name = (uploaded_file.name or "").lower()
    allowed = settings.ALLOWED_UPLOAD_EXTENSIONS
    if not any(name.endswith(ext) for ext in allowed):
        raise ValidationError(
            _("İzin verilmeyen dosya türü. İzin verilenler: %(list)s")
            % {"list": ", ".join(allowed)}
        )

    # Yol geçişi (path traversal) denemelerini engelle.
    if "/" in name or "\\" in name or ".." in name:
        raise ValidationError(_("Geçersiz dosya adı."))

    head = uploaded_file.read(16)
    uploaded_file.seek(0)
    if name.endswith((".csv", ".xlsx")):
        return  # metin/zip tabanlı; imza kontrolü uygulanmaz
    if not any(head.startswith(sig) for sig in _IMAGE_MAGIC):
        raise ValidationError(_("Dosya içeriği uzantısıyla uyuşmuyor. Yükleme reddedildi."))


def random_password(length: int = 14) -> str:
    """Politikaya uygun rastgele parola üretir."""
    pools = [string.ascii_lowercase, string.ascii_uppercase, string.digits, "!@#$%*?-_"]
    chars = [secrets.choice(pool) for pool in pools]
    everything = "".join(pools)
    chars += [secrets.choice(everything) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    return "".join(chars)
