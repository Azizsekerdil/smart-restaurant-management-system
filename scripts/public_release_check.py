"""Depo public yapılmadan önce çalıştırılması ZORUNLU yayın kapısı.

Kontroller:
  1. Gizli değer taraması (scripts/secret_scan.py, izlenen dosyalar).
  2. Yasak dosyaların git tarafından izlenmediği (dahili çalışma dizinleri,
     .env, veritabanı, yedek, log, medya, exe).
  3. .gitignore'da kritik kalıpların varlığı.
  4. Zorunlu belge dosyalarının varlığı (LICENSE, THIRD_PARTY_NOTICES.md ...).
  5. Runtime bağımlılık lisanslarının allowlist denetimi. Bilinmeyen lisans
     otomatik UYGUN sayılmaz; REVIEW_REQUIRED olarak raporlanır ve kapıyı
     kırmızıya çevirir (--allow-unknown ile yalnızca uyarıya düşer).

Herhangi bir kontrol başarısızsa sıfırdan farklı çıkış kodu döner ve depo
public YAPILMAMALIDIR. Bu script hukuki görüş vermez; teknik kapıdır.

Kullanım:
    python scripts/public_release_check.py
    python scripts/public_release_check.py --allow-unknown
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404
import sys
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------
#  1-2. Yasak izlenen dosyalar
# --------------------------------------------------------------------
FORBIDDEN_TRACKED_PATTERNS = [
    # Dahili/yayımlanmamış çalışma dizinleri. Bunlar ürünün parçası
    # değildir; depo kapsamı ve kurumsal hijyen gereği public depoda
    # bulunmazlar. DİKKAT: bir dosyayı şimdi silmek yetmez — git
    # GEÇMİŞİNDE kalır; public yapmadan önce geçmiş de denetlenmelidir.
    (re.compile(r"^patent/"), "dahili çalışma dizini (public depo kapsamı dışında)"),
    (
        re.compile(r"^\.claude/"),
        "ajan/asistan talimat dosyaları (public depo kapsamı dışında)",
    ),
    (
        re.compile(
            r"^(DISCOVERY_REPORT|HSP_PROJECT_REVIEW|PHASE_\d+_REPORT|"
            r"PUBLIC_RELEASE_READINESS|TEST_REPORT|PACKAGING_TEST|"
            r"IMPLEMENTATION_PLAN)\.md$"
        ),
        "dahili değerlendirme/durum raporu (public depo kapsamı dışında)",
    ),
    (re.compile(r"(^|/)\.env$"), ".env (gizli değerler)"),
    (re.compile(r"\.(sqlite3|sqlite3-wal|sqlite3-shm|db)$"), "veritabanı dosyası"),
    (re.compile(r"^backups/"), "yedek dosyaları"),
    (re.compile(r"^logs/"), "log dosyaları"),
    (re.compile(r"^media/(?!\.gitkeep$)"), "kullanıcı yüklemeleri"),
    (re.compile(r"\.(exe|pfx|p12|pem|key)$"), "çalıştırılabilir/anahtar dosyası"),
    (re.compile(r"^Uygulama/"), "paketlenmiş uygulama verisi"),
]

REQUIRED_GITIGNORE_ENTRIES = ["/patent/", ".env", "*.sqlite3", "logs/", "media/"]

REQUIRED_FILES = [
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "README.md",
    "SECURITY.md",
    ".env.example",
]

# --------------------------------------------------------------------
#  5. Lisans allowlist/denylist (SPDX kimlikleri ve yaygın eşdeğer adlar)
# --------------------------------------------------------------------
LICENSE_ALLOWLIST = [
    "MIT",
    "BSD",  # BSD-2/3-Clause varyantlarını kapsar
    "Apache",
    "ISC",
    "PSF",
    "Python Software Foundation",
    "ZPL",  # Zope Public License (Twisted bağımlılık zinciri)
    "MPL",  # zayıf copyleft; dosya bazlı, dağıtımı engellemez
]
# Sert engel: bu ailelerden bir RUNTIME bağımlılığı çıkarsa dağıtım modeli
# yeniden değerlendirilmeden yayın yapılmaz.
LICENSE_DENYLIST = ["GPL-3", "GPL v3", "AGPL", "SSPL", "BUSL", "BSL-1.1"]
# Bilinçli istisnalar: paket -> gerekçe (THIRD_PARTY_NOTICES.md ile uyumlu).
LICENSE_EXCEPTIONS = {
    "psycopg": "LGPL-3.0 — isteğe bağlı bağımlılık, dinamik bağlantı; dağıtılan exe'ye gömülmez",
    "psycopg-binary": "LGPL-3.0 — isteğe bağlı bağımlılık, dinamik bağlantı",
    "chardet": "LGPL — yalnızca dev bağımlılığı üzerinden gelir; dağıtılmaz",
}


def _tracked_files() -> list[str]:
    result = subprocess.run(  # nosec B603 B607
        ["git", "ls-files"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def check_forbidden_tracked(findings: list[str]) -> None:
    for path in _tracked_files():
        for pattern, label in FORBIDDEN_TRACKED_PATTERNS:
            if pattern.search(path):
                findings.append(f"İzlenmemesi gereken dosya izleniyor: {path} ({label})")


def check_gitignore(findings: list[str]) -> None:
    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        findings.append(".gitignore yok")
        return
    content = gitignore.read_text(encoding="utf-8")
    for entry in REQUIRED_GITIGNORE_ENTRIES:
        if entry not in content:
            findings.append(f".gitignore'da zorunlu kalıp eksik: {entry}")


def check_required_files(findings: list[str]) -> None:
    for name in REQUIRED_FILES:
        if not (ROOT / name).exists():
            findings.append(f"Zorunlu dosya eksik: {name}")


def check_secret_scan(findings: list[str]) -> None:
    result = subprocess.run(  # nosec B603
        [sys.executable, str(ROOT / "scripts" / "secret_scan.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        findings.append(
            "Gizli değer taraması BAŞARISIZ — ayrıntı için: python scripts/secret_scan.py"
        )


def _requirement_names(req_file: Path) -> list[str]:
    names = []
    if not req_file.exists():
        return names
    for line in req_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        name = re.split(r"[<>=!\[;]", line, maxsplit=1)[0].strip()
        if name:
            names.append(name)
    return names


def _distribution_license(name: str) -> str:
    """Kurulu paketin lisans bilgisini metadata'dan okur; yoksa UNKNOWN."""
    try:
        meta = metadata.metadata(name)
    except metadata.PackageNotFoundError:
        return "NOT_INSTALLED"
    classifiers = [
        c.split("::")[-1].strip()
        for c in meta.get_all("Classifier", [])
        if c.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    for field in ("License-Expression", "License"):
        value = meta.get(field, "")
        if value and value.strip().upper() not in {"", "UNKNOWN"}:
            # Uzun serbest metin lisanslarını kısalt
            return value.strip().splitlines()[0][:120]
    return "UNKNOWN"


def check_licenses(findings: list[str], warnings: list[str], *, allow_unknown: bool) -> None:
    names = _requirement_names(ROOT / "requirements.txt")
    for name in names:
        license_text = _distribution_license(name)
        key = name.lower()
        if key in LICENSE_EXCEPTIONS:
            warnings.append(f"{name}: istisna — {LICENSE_EXCEPTIONS[key]}")
            continue
        if license_text in {"NOT_INSTALLED"}:
            warnings.append(f"{name}: kurulu değil, lisans doğrulanamadı (REVIEW_REQUIRED)")
            continue
        upper = license_text.upper()
        if any(deny.upper() in upper for deny in LICENSE_DENYLIST):
            findings.append(f"{name}: yasaklı lisans ailesi tespit edildi -> {license_text}")
            continue
        if any(allow.upper() in upper for allow in LICENSE_ALLOWLIST):
            continue
        message = f"{name}: lisans allowlist dışı/bilinmiyor -> {license_text} (REVIEW_REQUIRED)"
        if allow_unknown:
            warnings.append(message)
        else:
            findings.append(message)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-unknown",
        action="store_true",
        help="Bilinmeyen lisansları hata değil uyarı say (insan incelemesi yine zorunlu)",
    )
    args = parser.parse_args()

    findings: list[str] = []
    warnings: list[str] = []

    check_forbidden_tracked(findings)
    check_gitignore(findings)
    check_required_files(findings)
    check_secret_scan(findings)
    check_licenses(findings, warnings, allow_unknown=args.allow_unknown)

    print("=" * 66)
    print("  PUBLIC YAYIN KAPISI")
    print("=" * 66)
    for warning in warnings:
        print(f"  UYARI : {warning}")
    for finding in findings:
        print(f"  HATA  : {finding}")
    if findings:
        print("-" * 66)
        print(f"  SONUÇ: NOT_READY — {len(findings)} engel. Depo public YAPILMAMALI.")
        print("=" * 66)
        return 1
    print("-" * 66)
    print("  SONUÇ: READY — teknik kapılar geçildi.")
    print("  Not: bu betik teknik bir kapıdır. Depo görünürlüğünü")
    print("  değiştirmeden önce ayrıca insan onayı alın.")
    print("=" * 66)
    return 0


if __name__ == "__main__":
    sys.exit(main())
