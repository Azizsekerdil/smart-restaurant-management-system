"""Günlük kayıtlarında hassas verilerin maskelenmesi.

Bu filtre tüm log handler'larına bağlıdır. API anahtarları, parolalar,
token'lar ve kişisel veriler diske veya konsola yazılmadan önce
maskelenir.
"""

from __future__ import annotations

import logging
import re

# Anahtar biçimleri: sağlayıcıya özgü önekler + genel "key=value" kalıpları
_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    # NVIDIA
    (re.compile(r"nvapi-[A-Za-z0-9_\-]{10,}"), "nvapi-***MASKELENDI***"),
    # OpenAI / OpenRouter
    (re.compile(r"sk-(?:proj-|or-v1-|ant-)?[A-Za-z0-9_\-]{16,}"), "sk-***MASKELENDI***"),
    # Google
    (re.compile(r"AIza[A-Za-z0-9_\-]{30,}"), "AIza***MASKELENDI***"),
    # GitHub
    (re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"), "gh*_***MASKELENDI***"),
    # AWS
    (re.compile(r"AKIA[0-9A-Z]{16}"), "AKIA***MASKELENDI***"),
    # JWT
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "***JWT***"),
    # key=... / token: "..." / password=...
    (
        re.compile(
            r"(?i)\b(api[_\-]?key|apikey|secret|token|password|passwd|pwd|authorization|bearer)"
            r"\b(\s*[:=]\s*|\s+)([\"']?)([^\s\"',;)]{6,})\3"
        ),
        r"\1\2\3***MASKELENDI***\3",
    ),
]

# Kişisel veriler (KVKK): tam e-posta ve telefonlar loglanmamalıdır.
_PII_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"\b([A-Za-z0-9._%+\-])[A-Za-z0-9._%+\-]*@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b"),
        r"\1***@\2",
    ),
    (
        re.compile(r"(?<!\d)(\+?90|0)?\s?5\d{2}[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}(?!\d)"),
        "05**-***-****",
    ),
]


def mask_secrets(text: str, *, mask_pii: bool = True) -> str:
    """Metindeki gizli değerleri ve isteğe bağlı olarak kişisel verileri maskeler."""
    if not text:
        return text
    result = text
    for pattern, replacement in _PATTERNS:
        result = pattern.sub(replacement, result)
    if mask_pii:
        for pattern, replacement in _PII_PATTERNS:
            result = pattern.sub(replacement, result)
    return result


class SensitiveDataFilter(logging.Filter):
    """Log kaydındaki mesaj ve argümanları maskeler."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = mask_secrets(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        k: mask_secrets(v) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        mask_secrets(a) if isinstance(a, str) else a for a in record.args
                    )
        except Exception:  # pragma: no cover - loglama asla uygulamayı düşürmemeli
            return True
        return True
