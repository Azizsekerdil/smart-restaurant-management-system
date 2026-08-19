"""Çeviri kataloğu araçları — GNU gettext kurulumu gerektirmez.

Neden kendi aracımız
--------------------
Django'nun ``makemessages`` / ``compilemessages`` komutları GNU gettext
ikililerine (``xgettext``, ``msgfmt``) ihtiyaç duyar. Bunlar Windows'ta
varsayılan olarak bulunmaz ve ayrı kurulum ister. Projenin tek komutla
Windows'ta çalışması hedeflendiği için, ihtiyaç duyulan iki işi (çıkarma
ve derleme) burada saf Python ile yapıyoruz.

Kullanım
--------
    python scripts/i18n_tools.py extract      # kaynaklardan metinleri topla
    python scripts/i18n_tools.py compile      # .po -> .mo
    python scripts/i18n_tools.py status       # çeviri kapsamını raporla

``extract`` mevcut çevirileri **korur**; yalnızca yeni metinleri ekler ve
kaynakta kalmayanları "eski" olarak işaretler.
"""

from __future__ import annotations

import ast
import importlib.util
import re
import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOCALE_DIR = PROJECT_ROOT / "locale"
LANGUAGES = ("en",)  # tr kaynak dildir, kataloğa gerek yok

SCAN_DIRS = ("apps", "config", "templates")
SKIP_PARTS = {"migrations", "__pycache__", ".venv", "node_modules", "staticfiles"}


# ==================================================================
#  Çıkarma
# ==================================================================
# {% trans "metin" %} / {% translate "metin" %}
TRANS_TAG = re.compile(r"""\{%\s*(?:trans|translate)\s+(["'])(.+?)\1""", re.S)
# {% blocktrans %}metin{% endblocktrans %}
BLOCKTRANS = re.compile(
    r"""\{%\s*blocktrans(?:late)?[^%]*%\}(.*?)\{%\s*endblocktrans(?:late)?\s*%\}""", re.S
)


def _python_strings(path: Path) -> set[str]:
    """_( ... ) ve gettext çağrılarındaki düz metinleri toplar.

    Kaynağı ayrıştırarak (parse) buluyoruz; düzenli ifade, iç içe
    parantezler ve kaçış dizileri yüzünden bu iş için güvenilmezdir.
    """
    names = {"_", "gettext", "gettext_lazy", "ngettext", "ugettext", "pgettext"}
    found: set[str] = set()
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return found

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not node.args:
            continue
        target = node.func
        label = getattr(target, "id", None) or getattr(target, "attr", None)
        if label not in names:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            text = first.value.strip()
            if text:
                found.add(text)
    return found


#: blocktrans gövdesindeki {{ değişken }} ifadeleri
BLOCK_VARIABLE = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def _blocktrans_msgid(body: str) -> str:
    """blocktrans gövdesini Django'nun ürettiği msgid'e çevirir.

    Django, ``{{ ad }}`` yer tutucularını katalogda ``%(ad)s`` biçiminde
    saklar. Ham şablon metnini kullanırsak anahtar tutmaz ve çeviri
    sessizce uygulanmaz — arayüzde metin Türkçe kalır.
    """
    return BLOCK_VARIABLE.sub(lambda match: f"%({match.group(1)})s", body).strip()


def _template_strings(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    found = {match.group(2).strip() for match in TRANS_TAG.finditer(text)}
    found |= {_blocktrans_msgid(match.group(1)) for match in BLOCKTRANS.finditer(text)}
    return {item for item in found if item}


def collect() -> dict[str, list[str]]:
    """Tüm çevrilebilir metinleri, geçtikleri yerlerle birlikte döndürür."""
    entries: dict[str, list[str]] = {}

    for folder in SCAN_DIRS:
        root = PROJECT_ROOT / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or any(part in SKIP_PARTS for part in path.parts):
                continue
            if path.suffix == ".py":
                strings = _python_strings(path)
            elif path.suffix == ".html":
                strings = _template_strings(path)
            else:
                continue
            location = str(path.relative_to(PROJECT_ROOT)).replace("\\", "/")
            for item in strings:
                entries.setdefault(item, []).append(location)

    return entries


# ==================================================================
#  .po okuma / yazma
# ==================================================================
def _unescape(text: str) -> str:
    return text.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"').replace("\\\\", "\\")


def _escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\t", "\\t")


def read_po(path: Path) -> dict[str, str]:
    """.po dosyasını {msgid: msgstr} olarak okur."""
    if not path.is_file():
        return {}

    catalog: dict[str, str] = {}
    msgid: list[str] = []
    msgstr: list[str] = []
    current: str | None = None

    def flush() -> None:
        if msgid:
            key = _unescape("".join(msgid))
            value = _unescape("".join(msgstr))
            if key:
                catalog[key] = value

    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            if line.startswith("#") and current is not None:
                continue
            continue
        if line.startswith("msgid "):
            flush()
            msgid, msgstr = [line[6:].strip().strip('"')], []
            current = "id"
        elif line.startswith("msgstr "):
            msgstr = [line[7:].strip().strip('"')]
            current = "str"
        elif line.startswith('"'):
            chunk = line.strip().strip('"')
            if current == "id":
                msgid.append(chunk)
            elif current == "str":
                msgstr.append(chunk)
    flush()
    catalog.pop("", None)  # başlık girdisi
    return catalog


HEADER = """# Akıllı Restaurant Yönetim Sistemi — {language} çeviri kataloğu
#
# Kaynak dil Türkçe'dir. Boş msgstr, o metnin henüz çevrilmediği
# anlamına gelir ve arayüzde Türkçe hâliyle görünür.
#
msgid ""
msgstr ""
"Project-Id-Version: smart-restaurant-management-system 1.3.0\\n"
"MIME-Version: 1.0\\n"
"Content-Type: text/plain; charset=UTF-8\\n"
"Content-Transfer-Encoding: 8bit\\n"
"Language: {language}\\n"
"Plural-Forms: nplurals=2; plural=(n != 1);\\n"
"""


def write_po(path: Path, catalog: dict[str, str], entries: dict[str, list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    language = path.parent.parent.name

    lines = [HEADER.format(language=language)]
    live = set(entries)

    for msgid in sorted(entries, key=str.casefold):
        for location in sorted(set(entries[msgid]))[:4]:
            lines.append(f"#: {location}")
        lines.append(f'msgid "{_escape(msgid)}"')
        lines.append(f'msgstr "{_escape(catalog.get(msgid, ""))}"')
        lines.append("")

    stale = {k: v for k, v in catalog.items() if k not in live and v}
    if stale:
        lines.append("# ---- Kaynakta artık bulunmayan çeviriler ----")
        lines.append("# Silmeden bırakıldı: metin geri gelirse çeviri kaybolmasın.")
        lines.append("")
        for msgid in sorted(stale, key=str.casefold):
            lines.append("#~ " + f'msgid "{_escape(msgid)}"')
            lines.append("#~ " + f'msgstr "{_escape(stale[msgid])}"')
            lines.append("")

    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


# ==================================================================
#  .mo derleme
# ==================================================================
def write_mo(po_path: Path, mo_path: Path) -> int:
    """.po dosyasını ikili .mo biçimine çevirir.

    Biçim GNU gettext belgelerinde tanımlıdır: sihirli sayı, iki tablo
    (özgün metinler ve çeviriler) ve karma tablo (isteğe bağlı, atlanır).
    """
    catalog = {k: v for k, v in read_po(po_path).items() if v}
    # Başlık girdisi (msgid "") olmadan bazı araçlar kod çözümlemesini
    # yapamaz; kodlama bilgisini oradan okurlar.
    catalog[""] = "Content-Type: text/plain; charset=UTF-8\n"

    keys = sorted(catalog)
    ids = b""
    strs = b""
    offsets = []
    for key in keys:
        value = catalog[key].encode("utf-8")
        key_bytes = key.encode("utf-8")
        offsets.append((len(ids), len(key_bytes), len(strs), len(value)))
        ids += key_bytes + b"\x00"
        strs += value + b"\x00"

    count = len(keys)
    key_start = 7 * 4 + 16 * count
    value_start = key_start + len(ids)

    key_offsets = []
    value_offsets = []
    for offset1, length1, offset2, length2 in offsets:
        key_offsets += [length1, offset1 + key_start]
        value_offsets += [length2, offset2 + value_start]

    output = struct.pack(
        "Iiiiiii",
        0x950412DE,  # sihirli sayı
        0,  # sürüm
        count,
        7 * 4,
        7 * 4 + count * 8,
        0,
        0,
    )
    output += struct.pack("i" * len(key_offsets + value_offsets), *(key_offsets + value_offsets))
    output += ids + strs

    mo_path.parent.mkdir(parents=True, exist_ok=True)
    mo_path.write_bytes(output)
    return count - 1  # başlık girdisi sayılmaz


# ==================================================================
#  Komutlar
# ==================================================================
def _seed(language: str) -> dict[str, str]:
    """Çeviri sözlüğünü yükler (bkz. scripts/translations_<dil>.py)."""
    module_path = Path(__file__).with_name(f"translations_{language}.py")
    if not module_path.is_file():
        return {}

    spec = importlib.util.spec_from_file_location(f"translations_{language}", module_path)
    if spec is None or spec.loader is None:  # pragma: no cover - olağandışı
        return {}
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, "TRANSLATIONS", {})


def cmd_extract() -> int:
    entries = collect()
    print(f"Kaynaklarda {len(entries)} çevrilebilir metin bulundu.\n")

    for language in LANGUAGES:
        po_path = LOCALE_DIR / language / "LC_MESSAGES" / "django.po"
        # Sözlükteki çeviriler temel alınır; .po dosyasına elle eklenmiş
        # çeviriler varsa onlar korunur ve üzerine yazılmaz.
        # NOT: yalnızca DOLU .po girdileri sözlüğün üzerine yazar. Boş
        # msgstr'ler de birleştirilirse sözlükteki çeviriler silinir.
        manual = {k: v for k, v in read_po(po_path).items() if v}
        existing = {**_seed(language), **manual}
        write_po(po_path, existing, entries)

        translated = sum(1 for k in entries if existing.get(k))
        print(f"  {language}: {po_path.relative_to(PROJECT_ROOT)}")
        print(f"      {translated}/{len(entries)} çevrilmiş, {len(entries) - translated} eksik")
    return 0


def cmd_compile() -> int:
    total = 0
    for language in LANGUAGES:
        po_path = LOCALE_DIR / language / "LC_MESSAGES" / "django.po"
        if not po_path.is_file():
            print(f"  {language}: .po yok, önce extract çalıştırın")
            continue
        mo_path = po_path.with_suffix(".mo")
        count = write_mo(po_path, mo_path)
        total += count
        print(f"  {language}: {count} çeviri -> {mo_path.relative_to(PROJECT_ROOT)}")
    print(f"\nToplam {total} çeviri derlendi.")
    return 0


def cmd_status() -> int:
    entries = collect()
    print(f"Kaynaklarda {len(entries)} çevrilebilir metin var.\n")
    for language in LANGUAGES:
        po_path = LOCALE_DIR / language / "LC_MESSAGES" / "django.po"
        catalog = {**_seed(language), **read_po(po_path)}
        translated = [k for k in entries if catalog.get(k)]
        missing = [k for k in entries if not catalog.get(k)]
        percent = round(len(translated) / len(entries) * 100, 1) if entries else 0
        print(f"  {language}: %{percent} ({len(translated)}/{len(entries)})")
        if missing:
            print("      eksik ilk 15:")
            for item in sorted(missing, key=str.casefold)[:15]:
                print(f"        - {item[:80]}")
    return 0


COMMANDS = {"extract": cmd_extract, "compile": cmd_compile, "status": cmd_status}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        return 1
    return COMMANDS[sys.argv[1]]()


if __name__ == "__main__":
    sys.exit(main())
