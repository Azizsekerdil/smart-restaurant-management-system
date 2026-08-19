"""Güvenli terminal çalıştırıcısı.

Güvenlik modeli (savunma katmanları)
------------------------------------
1. **Allowlist**: Yalnızca önceden tanımlı programlar çalıştırılabilir.
   Bilinmeyen her komut reddedilir (deny-by-default).
2. **Kabuk yok**: `shell=False` ile çalışır; `&&`, `|`, `;`, `>` gibi
   kabuk operatörleri yorumlanmaz, dolayısıyla komut zinciri kurulamaz.
3. **Yol hapsi**: Çalışma dizini `DEVCENTER_ROOT` dışına çıkamaz; argüman
   olarak verilen yollar da bu kökün içinde olmak zorundadır.
4. **Tehlikeli kalıp reddi**: Silme, biçimlendirme, kayıt defteri, kullanıcı
   yönetimi ve kimlik bilgisi okuma kalıpları açıkça engellenir.
5. **Onay kapısı**: Etkili komutlar (pip install, git commit, migrate...)
   kullanıcı onayı olmadan çalışmaz.
6. **Zaman aşımı + kayıt**: Her çalıştırma süre sınırlıdır ve
   `CommandRun` olarak kayda geçer. Çıktıdaki gizli değerler maskelenir.
"""

from __future__ import annotations

import os
import re
import shlex
import subprocess  # nosec B404
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.core.logging_filters import mask_secrets

# --------------------------------------------------------------------
#  İzin verilen programlar ve alt komutlar
#  None => tüm argümanlar serbest (yine de tehlikeli kalıp taraması yapılır)
# --------------------------------------------------------------------
ALLOWED_COMMANDS: dict[str, set[str] | None] = {
    "python": None,
    "py": None,
    "pytest": None,
    "ruff": None,
    "black": None,
    "mypy": None,
    "bandit": None,
    "pip": {"list", "show", "freeze", "check", "install", "--version"},
    "npm": {"list", "run", "test", "ci", "install", "--version"},
    "npx": None,
    "git": {
        "status",
        "diff",
        "log",
        "branch",
        "show",
        "add",
        "commit",
        "checkout",
        "switch",
        "stash",
        "restore",
        "remote",
        "rev-parse",
        "config",
        "--version",
    },
    "docker": {"compose", "ps", "images", "--version"},
}

# Kullanıcı onayı gerektiren komutlar (yan etkisi olanlar)
#: (program, komutta bulunması gereken TÜM belirteçler)
CONFIRMATION_REQUIRED: list[tuple[str, tuple[str, ...]]] = [
    ("pip", ("install",)),
    ("npm", ("install",)),
    ("npm", ("ci",)),
    ("git", ("commit",)),
    ("git", ("add",)),
    ("git", ("checkout",)),
    ("git", ("switch",)),
    ("git", ("restore",)),
    ("git", ("stash",)),
    ("docker", ("compose",)),
    ("python", ("manage.py", "migrate")),
    ("python", ("manage.py", "makemigrations")),
    ("python", ("manage.py", "flush")),
    ("python", ("manage.py", "loaddata")),
]

# Hiçbir koşulda çalıştırılmayacak kalıplar
FORBIDDEN_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\brm\b|\brmdir\b|\bdel\b|\berase\b", re.I), "Dosya silme komutları engellidir."),
    (
        re.compile(r"Remove-Item|Clear-Content|Set-Content", re.I),
        "PowerShell dosya işlemleri engellidir.",
    ),
    (re.compile(r"\bformat\b|\bdiskpart\b|\bmkfs\b|\bfdisk\b", re.I), "Disk işlemleri engellidir."),
    (
        re.compile(r"\breg\b\s+(add|delete|import)|Set-ItemProperty|HKLM|HKCU", re.I),
        "Kayıt defteri işlemleri engellidir.",
    ),
    (
        re.compile(r"net\s+user|net\s+localgroup|Add-LocalUser|useradd|passwd", re.I),
        "Kullanıcı yönetimi engellidir.",
    ),
    (
        re.compile(r"shutdown|restart-computer|taskkill|Stop-Process|kill\s+-9", re.I),
        "Süreç/sistem sonlandırma engellidir.",
    ),
    (
        re.compile(r"curl|wget|Invoke-WebRequest|Invoke-RestMethod", re.I),
        "Doğrudan ağ indirme engellidir.",
    ),
    (
        re.compile(r"\bcat\b|\btype\b|Get-Content", re.I),
        "Dosya okuma için terminal yerine kod görüntüleyiciyi kullanın.",
    ),
    (
        re.compile(r"\.env\b", re.I),
        "'.env' dosyasına terminalden erişim engellidir (gizli anahtarlar).",
    ),
    (
        re.compile(r"id_rsa|\.ssh|credential|password|secret|token|apikey|api_key", re.I),
        "Kimlik bilgisi içeren yollar engellidir.",
    ),
    (re.compile(r"[;&|]{1,2}|`|\$\(", re.S), "Komut zincirleme ve ikame karakterleri engellidir."),
    (re.compile(r">>?\s*\S|<\s*\S"), "Çıktı yönlendirme engellidir."),
    (
        re.compile(r"git\s+push", re.I),
        "'git push' terminalden yapılamaz; yükleme işlemi ayrı onay gerektirir.",
    ),
    (
        re.compile(r"git\s+reset\s+--hard|git\s+clean\s+-\w*f", re.I),
        "Geri alınamaz git komutları engellidir.",
    ),
    (
        re.compile(r"manage\.py\s+(flush|sqlflush|dbshell)", re.I),
        "Veritabanını boşaltan komutlar engellidir.",
    ),
    (re.compile(r"DROP\s+TABLE|TRUNCATE|DELETE\s+FROM", re.I), "Yıkıcı SQL ifadeleri engellidir."),
]


@dataclass
class CommandCheck:
    allowed: bool
    reason: str = ""
    needs_confirmation: bool = False
    parts: list[str] | None = None


def project_root() -> Path:
    return Path(settings.DEVCENTER["ROOT"]).resolve()


def is_inside_root(path: str | Path) -> bool:
    """Verilen yolun proje kökü içinde olup olmadığını kontrol eder."""
    root = project_root()
    try:
        candidate = (
            (root / Path(path)).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        )
    except (OSError, ValueError):
        return False
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def check_command(command: str) -> CommandCheck:
    """Komutu çalıştırmadan önce güvenlik denetiminden geçirir."""
    raw = (command or "").strip()
    if not raw:
        return CommandCheck(False, "Boş komut.")
    if len(raw) > 800:
        return CommandCheck(False, "Komut çok uzun (en fazla 800 karakter).")

    for pattern, reason in FORBIDDEN_PATTERNS:
        if pattern.search(raw):
            return CommandCheck(False, reason)

    try:
        parts = shlex.split(raw, posix=False)
    except ValueError as exc:
        return CommandCheck(False, f"Komut ayrıştırılamadı: {exc}")
    if not parts:
        return CommandCheck(False, "Boş komut.")

    program = Path(parts[0].strip('"')).name.lower()
    program = program[:-4] if program.endswith(".exe") else program

    if program not in ALLOWED_COMMANDS:
        allowed = ", ".join(sorted(ALLOWED_COMMANDS))
        return CommandCheck(
            False,
            f"'{program}' izin verilen komutlar listesinde değil. İzin verilenler: {allowed}",
        )

    allowed_subcommands = ALLOWED_COMMANDS[program]
    if allowed_subcommands is not None:
        subcommand = parts[1].lower() if len(parts) > 1 else ""
        if subcommand not in allowed_subcommands:
            return CommandCheck(
                False,
                f"'{program} {subcommand}' izinli değil. "
                f"İzin verilen alt komutlar: {', '.join(sorted(allowed_subcommands))}",
            )

    # Argümanlardaki yolların proje kökü içinde olduğunu doğrula.
    for argument in parts[1:]:
        clean = argument.strip('"').strip("'")
        if clean.startswith("-"):
            continue
        if ".." in clean.replace("\\", "/").split("/"):
            return CommandCheck(False, "Üst dizine çıkan yollar ('..') engellidir.")
        if Path(clean).is_absolute() and not is_inside_root(clean):
            return CommandCheck(
                False,
                f"'{clean}' proje klasörü dışında. Yalnızca {project_root()} içinde çalışılabilir.",
            )

    lowered = [p.lower().strip('"') for p in parts]
    needs_confirmation = False
    for prog, sequence in CONFIRMATION_REQUIRED:
        if program != prog:
            continue
        if all(token in lowered for token in sequence):
            needs_confirmation = True
            break

    return CommandCheck(True, "", needs_confirmation, parts)


def run_command(
    command: str,
    *,
    user=None,
    confirmed: bool = False,
    timeout: int | None = None,
):
    """Komutu güvenli biçimde çalıştırır ve `CommandRun` kaydı döndürür."""
    from apps.core.models import AuditLog
    from apps.core.services import record_audit
    from apps.devcenter.models import CommandRun

    root = project_root()
    timeout = timeout or settings.DEVCENTER["COMMAND_TIMEOUT"]

    if not settings.DEVCENTER["TERMINAL_ENABLED"]:
        return CommandRun.objects.create(
            user=user,
            command=command[:1000],
            working_directory=str(root),
            status=CommandRun.Status.BLOCKED,
            block_reason="Güvenli terminal bu ortamda kapalıdır (DEVCENTER_TERMINAL_ENABLED=False).",
        )

    check = check_command(command)
    if not check.allowed:
        run = CommandRun.objects.create(
            user=user,
            command=command[:1000],
            working_directory=str(root),
            status=CommandRun.Status.BLOCKED,
            block_reason=check.reason[:300],
        )
        record_audit(
            AuditLog.Action.TERMINAL,
            user=user,
            obj=run,
            description=f"Engellenen komut: {command[:200]} — {check.reason}",
            severity=AuditLog.Severity.WARNING,
        )
        return run

    if check.needs_confirmation and not confirmed:
        return CommandRun.objects.create(
            user=user,
            command=command[:1000],
            working_directory=str(root),
            status=CommandRun.Status.PENDING,
            required_confirmation=True,
            block_reason="Bu komut yan etkili olduğu için kullanıcı onayı gerektirir.",
        )

    run = CommandRun.objects.create(
        user=user,
        command=command[:1000],
        working_directory=str(root),
        status=CommandRun.Status.RUNNING,
        required_confirmation=check.needs_confirmation,
        confirmed_at=None,
    )

    # Alt sürece yalnızca gerekli ortam değişkenleri aktarılır; API
    # anahtarları ve gizli değerler dışarıda bırakılır.
    safe_env = _sanitized_env()
    started = time.perf_counter()
    try:
        completed = subprocess.run(  # nosec B603
            check.parts,
            cwd=str(root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            shell=False,
            env=safe_env,
        )
        run.exit_code = completed.returncode
        run.stdout = mask_secrets(completed.stdout or "")[:60000]
        run.stderr = mask_secrets(completed.stderr or "")[:20000]
        run.status = (
            CommandRun.Status.SUCCESS if completed.returncode == 0 else CommandRun.Status.FAILED
        )
    except subprocess.TimeoutExpired:
        run.status = CommandRun.Status.TIMEOUT
        run.stderr = f"Komut {timeout} saniye içinde tamamlanmadı ve durduruldu."
    except FileNotFoundError:
        run.status = CommandRun.Status.FAILED
        run.stderr = f"'{check.parts[0]}' bulunamadı. Program kurulu mu?"
    except Exception as exc:  # pragma: no cover
        run.status = CommandRun.Status.FAILED
        run.stderr = mask_secrets(f"Beklenmeyen hata: {exc}")[:2000]

    run.duration_ms = int((time.perf_counter() - started) * 1000)
    run.save()

    record_audit(
        AuditLog.Action.TERMINAL,
        user=user,
        obj=run,
        description=f"Komut çalıştırıldı: {command[:200]} -> {run.get_status_display()}",
        severity=(AuditLog.Severity.NOTICE if run.succeeded else AuditLog.Severity.WARNING),
    )
    return run


def _sanitized_env() -> dict[str, str]:
    """Alt sürece gizli anahtar sızdırmayan ortam değişkeni kümesi."""
    blocked_markers = (
        "API_KEY",
        "APIKEY",
        "SECRET",
        "TOKEN",
        "PASSWORD",
        "PASSWD",
        "CREDENTIAL",
        "PRIVATE",
    )
    env = {
        key: value
        for key, value in os.environ.items()
        if not any(marker in key.upper() for marker in blocked_markers)
    }
    env["DJANGO_SETTINGS_MODULE"] = "config.settings"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def command_help() -> list[dict]:
    """Arayüzde gösterilecek izinli komut listesi."""
    rows = []
    for program, subcommands in sorted(ALLOWED_COMMANDS.items()):
        confirm = [s for p, s in CONFIRMATION_REQUIRED if p == program]
        rows.append(
            {
                "program": program,
                "subcommands": sorted(subcommands) if subcommands else "tüm argümanlar",
                "needs_confirmation": [" ".join(c) for c in confirm],
            }
        )
    return rows
