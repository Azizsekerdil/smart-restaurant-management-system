"""Projeyi KAYNAKTAN ölçen sayaçlar.

Neden?
------
Tanıtım sunumundaki "350 test", "60+ izin", "11 modül" gibi sayılar elle
yazıldığında sessizce eskir ve yayımlanan belge yanlış bilgi verir. Bu
modül aynı sayıları her üretimde depodan ölçer; sunum, README ve yayın
manifestosu tek bir doğruluk kaynağını kullanır.

Ölçümler ağ ya da çalışan sunucu gerektirmez ve hiçbir şeyi tahmin etmez;
sayamadığı bir şey için sayı üretmez.

Kullanım:
    python scripts/project_metrics.py            # okunabilir çıktı
    python scripts/project_metrics.py --json     # makine-okunur
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ testler
def count_tests() -> int | None:
    """pytest'in TOPLADIĞI test sayısı.

    Kaynağı elle ayrıştırmak yerine pytest'e sorulur: parametreli testler,
    fikstür türetmeleri ve atlanan dosyalar ancak toplayıcı tarafından
    doğru sayılır. pytest yoksa ya da toplama başarısızsa ``None`` döner —
    sunum o zaman sayıyı hiç yazmaz. Yanlış bir sayı yazmaktansa hiç
    yazmamak doğrudur.
    """
    import subprocess  # nosec B404 - sabit argümanlı, kabuk kullanılmayan çağrı

    try:
        result = subprocess.run(  # nosec B603
            [sys.executable, "-m", "pytest", "--collect-only", "-q"],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=600,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    match = re.search(r"(\d+)\s+tests?\s+collected", result.stdout or "")
    if not match:
        return None
    return int(match.group(1))


# ------------------------------------------------------------------ kod
def count_local_apps() -> int:
    text = (PROJECT_ROOT / "config" / "settings.py").read_text(encoding="utf-8")
    match = re.search(r"LOCAL_APPS\s*=\s*\[(.*?)\]", text, re.S)
    if not match:
        return 0
    return len(re.findall(r'"apps\.[a-z_]+"', match.group(1)))


def _permissions_module() -> ast.Module:
    path = PROJECT_ROOT / "apps" / "accounts" / "permissions.py"
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def count_permission_codes() -> int:
    for node in ast.walk(_permissions_module()):
        if isinstance(node, ast.AnnAssign) and getattr(node.target, "id", "") == "PERMISSIONS":
            if isinstance(node.value, ast.Dict):
                return len(node.value.keys)
    return 0


def count_roles() -> int:
    for node in ast.walk(_permissions_module()):
        if isinstance(node, ast.ClassDef) and node.name == "Role":
            return sum(1 for item in node.body if isinstance(item, ast.Assign))
    return 0


def count_templates() -> int:
    """Kullanıcıya görünen şablon sayısı (parça şablonlar hariç)."""
    return sum(
        1 for path in (PROJECT_ROOT / "templates").rglob("*.html") if not path.name.startswith("_")
    )


def count_models() -> int | None:
    """Uygulamanın kendi modellerinin (veritabanı tablolarının) sayısı.

    Django'ya sorulur: soyut ara sınıflardan türeyen modeller kaynak
    ayrıştırmasıyla gözden kaçıyordu. Django kurulamazsa ``None`` döner.
    """
    try:
        import django

        os_environ_setdefault = __import__("os").environ.setdefault
        os_environ_setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        os_environ_setdefault("DJANGO_ENV", "test")
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        django.setup()
        from django.apps import apps as django_apps
    except Exception:  # noqa: BLE001 - ölçüm aracı uygulamayı çökertmemeli
        return None
    return sum(
        1
        for model in django_apps.get_models()
        if model._meta.app_config is not None and model._meta.app_config.name.startswith("apps.")
    )


def count_url_routes() -> int:
    """``urls.py`` dosyalarındaki ``path()``/``re_path()`` sayısı."""
    total = 0
    for path in sorted(PROJECT_ROOT.rglob("urls.py")):
        if ".venv" in path.parts or "site-packages" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        total += len(re.findall(r"\b(?:path|re_path)\(", text))
    for name in ("api_urls.py", "routing.py"):
        for path in sorted(PROJECT_ROOT.rglob(name)):
            if ".venv" in path.parts:
                continue
            text = path.read_text(encoding="utf-8")
            total += len(re.findall(r"\b(?:path|re_path)\(", text))
    return total


def count_translated_strings() -> int:
    """İngilizce kataloğunda ÇEVİRİSİ DOLU olan metin sayısı."""
    po = PROJECT_ROOT / "locale" / "en" / "LC_MESSAGES" / "django.po"
    if not po.is_file():
        return 0
    text = po.read_text(encoding="utf-8")
    # msgid "..."\nmsgstr "..."  — msgstr boş olanlar çevrilmemiştir.
    entries = re.findall(
        r'^msgid\s+("(?:[^"\\]|\\.)*"(?:\s*\n"(?:[^"\\]|\\.)*")*)\s*\n'
        r'msgstr\s+("(?:[^"\\]|\\.)*"(?:\s*\n"(?:[^"\\]|\\.)*")*)',
        text,
        re.M,
    )
    translated = 0
    for msgid, msgstr in entries:
        if msgid.strip() == '""':
            continue  # başlık girdisi
        if re.sub(r'["\s]', "", msgstr):
            translated += 1
    return translated


def collect() -> dict[str, int | None]:
    """Tüm ölçümler. Ölçülemeyen değer ``None`` döner, uydurulmaz."""
    return {
        "tests": count_tests(),
        "modules": count_local_apps(),
        "roles": count_roles(),
        "permission_codes": count_permission_codes(),
        "screens": count_templates(),
        "database_tables": count_models(),
        "url_routes": count_url_routes(),
        "translated_strings": count_translated_strings(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="JSON olarak yaz")
    args = parser.parse_args()
    metrics = collect()
    if args.json:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
    else:
        width = max(len(k) for k in metrics)
        for key, value in metrics.items():
            print(f"{key:<{width}}  {'ölçülemedi' if value is None else value}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
