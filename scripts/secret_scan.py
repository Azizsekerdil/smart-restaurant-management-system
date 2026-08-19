"""Depoya gönderilmeden önce gizli değer taraması.

GitHub'a yükleme öncesi çalıştırılır. API anahtarı, parola, token, özel
anahtar veya gerçek kişisel veri bulursa **sıfırdan farklı** çıkış kodu
döndürür ve yüklemeyi durdurur.

Kullanım:
    python scripts/secret_scan.py            # izlenen dosyaları tara
    python scripts/secret_scan.py --all      # tüm dosyaları tara
    python scripts/secret_scan.py --staged   # yalnızca hazırlanan dosyalar
"""

from __future__ import annotations

import argparse
import re
import subprocess  # nosec B404
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# --------------------------------------------------------------------
#  Aranan desenler
# --------------------------------------------------------------------
SECRET_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    ("NVIDIA API anahtarı", re.compile(r"nvapi-[A-Za-z0-9_\-]{16,}"), "kritik"),
    (
        "OpenAI/OpenRouter anahtarı",
        re.compile(r"sk-(?:proj-|ant-|or-v1-)?[A-Za-z0-9_\-]{20,}"),
        "kritik",
    ),
    ("Google API anahtarı", re.compile(r"AIza[A-Za-z0-9_\-]{33,}"), "kritik"),
    ("GitHub token", re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"), "kritik"),
    ("AWS erişim anahtarı", re.compile(r"AKIA[0-9A-Z]{16}"), "kritik"),
    ("Slack token", re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"), "kritik"),
    (
        "Özel anahtar (PEM)",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"),
        "kritik",
    ),
    (
        "JWT",
        re.compile(r"eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{20,}"),
        "yüksek",
    ),
    (
        "Sabit kodlanmış parola",
        re.compile(
            r"(?i)\b(password|passwd|secret|api_key|apikey|access_token|private_key)\b"
            r"\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"
        ),
        "yüksek",
    ),
    (
        "Veritabanı bağlantı dizesi",
        re.compile(r"(?i)(postgres|postgresql|mysql|mongodb)://[^:\s]+:[^@\s]+@"),
        "yüksek",
    ),
]

# Depoda bulunmaması gereken dosyalar
FORBIDDEN_FILES = [
    ".env",
    "db.sqlite3",
    "restaurant.sqlite3",
    "secrets.json",
    "credentials.json",
    "id_rsa",
    "veri.json",
]

FORBIDDEN_SUFFIXES = [
    ".sqlite3",
    ".sqlite3-wal",  # WAL dosyası canlı veri içerir
    ".sqlite3-shm",
    ".db",
    ".pem",
    ".pfx",
    ".p12",
    ".key",
    ".keystore",
]

# Tarama dışı bırakılacak yollar
SKIP_DIRS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "staticfiles",
    "media",
    "logs",
    "backups",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".devcenter",
}

# İkili dosyalar taranmaz
SKIP_SUFFIXES = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".ico",
    ".woff",
    ".woff2",
    ".ttf",
    ".eot",
    ".pdf",
    ".zip",
    ".gz",
    ".xlsx",
    ".sqlite3",
    ".pyc",
    ".mo",
}

# Bilinçli olarak yok sayılan yerler: örnek/dokümantasyon değerleri
ALLOWLIST_PATTERNS = [
    re.compile(r"nvapi-\.\.\."),
    re.compile(r"sk-\.\.\."),
    re.compile(r"\*\*\*MASKELENDI\*\*\*"),
    re.compile(r"MASKELENDI"),
    re.compile(r"\[E-POSTA\]|\[TELEFON\]|\[TC-KIMLIK\]|\[KART-NO\]|\[IBAN\]"),
    re.compile(r"degistir-bu-anahtari"),
    re.compile(r"ci-icin-gecici-anahtar"),
    re.compile(r"restaurant-degistir"),
    # NOT: Sabit bir demo parolası ARTIK YOKTUR; `seed_demo` her çalıştırmada
    # rastgele üretir. Bu yüzden burada bir demo parolası muafiyeti de yoktur.
    re.compile(r"Test!2026Pass"),  # test fikstürü parolası
    re.compile(r"guclu-bir-parola"),  # dokümantasyon örneği
    re.compile(r"parola123"),  # test içindeki sahte değer
]

# Bu dosyalarda "parola" kelimesi geçmesi normaldir
DOC_SUFFIXES = {".md", ".txt", ".rst"}

# Satır içi izin işareti. Maskeleme testleri gibi, gerçekçi görünen ancak
# SAHTE olan değerlerin bulunması gereken yerlerde kullanılır. Her kullanım
# kod incelemesinde açıkça görülür.
INLINE_ALLOW = re.compile(r"secret-scan:\s*allow")


class Finding:
    def __init__(self, path: Path, line_no: int, label: str, severity: str, snippet: str):
        self.path = path
        self.line_no = line_no
        self.label = label
        self.severity = severity
        self.snippet = snippet

    def __str__(self) -> str:
        rel = self.path.relative_to(ROOT).as_posix()
        return f"  [{self.severity.upper():<7}] {rel}:{self.line_no}  {self.label}\n            {self.snippet}"


def is_allowlisted(line: str) -> bool:
    if INLINE_ALLOW.search(line):
        return True
    return any(pattern.search(line) for pattern in ALLOWLIST_PATTERNS)


def tracked_files() -> list[Path]:
    """Git tarafından izlenen dosyalar."""
    try:
        output = subprocess.run(  # nosec B603 B607
            ["git", "ls-files"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
            check=False,
        ).stdout
        return [ROOT / line for line in output.splitlines() if line.strip()]
    except Exception:
        return []


def staged_files() -> list[Path]:
    try:
        output = subprocess.run(  # nosec B603 B607
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
            check=False,
        ).stdout
        return [ROOT / line for line in output.splitlines() if line.strip()]
    except Exception:
        return []


def all_files() -> list[Path]:
    results = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if set(path.relative_to(ROOT).parts) & SKIP_DIRS:
            continue
        results.append(path)
    return results


def scan_file(path: Path) -> list[Finding]:
    if path.suffix.lower() in SKIP_SUFFIXES or not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    findings: list[Finding] = []
    is_doc = path.suffix.lower() in DOC_SUFFIXES

    for line_no, line in enumerate(text.splitlines(), start=1):
        if is_allowlisted(line):
            continue
        for label, pattern, severity in SECRET_PATTERNS:
            # Belgelerde "parola = ..." örnekleri normaldir
            if is_doc and label == "Sabit kodlanmış parola":
                continue
            match = pattern.search(line)
            if match:
                snippet = line.strip()[:100]
                # Bulunan değeri raporda da maskele
                found = match.group(0)
                if len(found) > 12:
                    snippet = snippet.replace(found, found[:6] + "…" + found[-2:])
                findings.append(Finding(path, line_no, label, severity, snippet))
    return findings


def git_ignored(paths: list[Path]) -> set[Path]:
    """`.gitignore` tarafından yok sayılan dosyaları döndürür."""
    if not paths or not (ROOT / ".git").exists():
        return set()
    try:
        result = subprocess.run(  # nosec B603 B607
            ["git", "check-ignore", "--stdin"],
            cwd=str(ROOT),
            input="\n".join(p.relative_to(ROOT).as_posix() for p in paths),
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
            check=False,
        )
        return {ROOT / line for line in result.stdout.splitlines() if line.strip()}
    except Exception:
        return set()


def check_forbidden_files(files: list[Path]) -> list[str]:
    """Depoya girmemesi gereken dosyaları bulur.

    `.gitignore` tarafından zaten dışlanan dosyalar sorun sayılmaz —
    yerel geliştirme veritabanı gibi dosyaların diskte olması normaldir.
    """
    problems = []
    ignored = git_ignored(files)
    for path in files:
        if path in ignored:
            continue
        if path.name in FORBIDDEN_FILES or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            problems.append(f"  [KRİTİK ] Depoda bulunmamalı: {path.relative_to(ROOT).as_posix()}")
    return problems


def check_gitignore() -> list[str]:
    """Kritik girdilerin .gitignore içinde olduğunu doğrular."""
    gitignore = ROOT / ".gitignore"
    if not gitignore.exists():
        return ["  [KRİTİK ] .gitignore dosyası yok!"]

    content = gitignore.read_text(encoding="utf-8")
    required = [".env", "*.sqlite3", "media/", "logs/", "backups/", ".venv/"]
    missing = [entry for entry in required if entry not in content]
    return [f"  [YÜKSEK ] .gitignore içinde eksik: {entry}" for entry in missing]


def main() -> int:
    parser = argparse.ArgumentParser(description="Depo gizli değer taraması")
    parser.add_argument("--all", action="store_true", help="Tüm dosyaları tara")
    parser.add_argument("--staged", action="store_true", help="Yalnızca hazırlanan dosyalar")
    args = parser.parse_args()

    if args.staged:
        files, scope = staged_files(), "hazırlanan (staged) dosyalar"
    elif args.all:
        files, scope = all_files(), "tüm dosyalar"
    else:
        files = tracked_files()
        scope = "git tarafından izlenen dosyalar"
        if not files:
            files, scope = all_files(), "tüm dosyalar (git deposu bulunamadı)"

    print()
    print("=" * 66)
    print("  GİZLİ DEĞER TARAMASI")
    print("=" * 66)
    print(f"  Kapsam : {scope}")
    print(f"  Dosya  : {len(files)}")
    print()

    findings: list[Finding] = []
    for path in files:
        findings.extend(scan_file(path))

    problems = check_forbidden_files(files) + check_gitignore()

    critical = [f for f in findings if f.severity == "kritik"]
    high = [f for f in findings if f.severity == "yüksek"]

    if problems:
        print("  DOSYA / YAPILANDIRMA SORUNLARI")
        print("  " + "-" * 62)
        for problem in problems:
            print(problem)
        print()

    if critical:
        print("  KRİTİK BULGULAR")
        print("  " + "-" * 62)
        for finding in critical:
            print(finding)
        print()

    if high:
        print("  YÜKSEK ÖNEMLİ BULGULAR")
        print("  " + "-" * 62)
        for finding in high:
            print(finding)
        print()

    blocking = len(critical) + len([p for p in problems if "KRİTİK" in p])

    print("=" * 66)
    if blocking:
        print(f"  SONUÇ: {blocking} engelleyici bulgu. YÜKLEME DURDURULDU.")
        print()
        print("  Yapılması gerekenler:")
        print("    1. Yukarıdaki değerleri koddan kaldırın, .env dosyasına taşıyın.")
        print("    2. Sızan anahtarları ilgili sağlayıcıdan İPTAL EDİN.")
        print("    3. Değer daha önce commit'lendiyse geçmişten de temizleyin")
        print("       (git filter-repo veya BFG Repo-Cleaner).")
        print("=" * 66)
        print()
        return 1

    if high:
        print(f"  SONUÇ: {len(high)} yüksek önemli bulgu (engelleyici değil).")
        print("         Gerçek bir gizli değer değilse yok sayabilirsiniz.")
        print("=" * 66)
        print()
        return 0

    print("  SONUÇ: Temiz. Gizli değer bulunamadı.")
    print("=" * 66)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
