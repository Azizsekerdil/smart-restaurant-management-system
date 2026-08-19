"""Şablonlardaki düz metinleri çeviri etiketiyle işaretler.

Neden bir araç
--------------
92 şablonu elle işaretlemek hem uzun sürer hem de tutarsızlık üretir.
Bu araç yalnızca **güvenli** durumları dönüştürür ve şüpheli her şeyi
olduğu gibi bırakır; kalanlar `--report` ile listelenir ve elle
işaretlenir.

Güvenli kabul edilen: **bir etiketin içeriğinin tamamını** oluşturan düz
metin (``<button>Kaydet</button>``) ve ``title`` / ``placeholder`` /
``aria-label`` / ``alt`` öznitelikleri.

Bu kural bilinçlidir. "İki etiket arasındaki her metin" kuralı, satır içi
etiketlerin böldüğü cümleleri parçalara ayırır: ``Sistem <code>.env</code>
dosyasını okur`` üç ayrı parça olur ve "dosyasını okur" gibi tek başına
çevrilemeyen diziler kataloğa girer. Yalnızca tam içerikleri alarak bundan
kaçınıyoruz.

Dokunulmayan: ``<script>`` ve ``<style>`` içeriği, HTML yorumları,
değişken içeren metinler (bunlar ``{% blocktrans %}`` ister ve anlamı
insan kararı gerektirir), satır içi etiketlerle bölünmüş cümleler,
yalnızca sayı/noktalama olan diziler.

Kullanım
--------
    python scripts/mark_templates.py --report      # ne olacağını göster
    python scripts/mark_templates.py --apply       # uygula
    python scripts/mark_templates.py --apply templates/orders   # tek klasör
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = PROJECT_ROOT / "templates"

#: İşaretlenecek öznitelikler
ATTRIBUTES = ("title", "placeholder", "aria-label", "alt")

#: Bu bloklar tamamen atlanır.
#: <code> ve <pre>: komut ve kod örnekleri çevrilmemelidir —
#: "python manage.py migrate" her dilde aynıdır.
SKIP_BLOCKS = re.compile(
    r"<script\b.*?</script>|<style\b.*?</style>|<code\b.*?</code>|<pre\b.*?</pre>|<!--.*?-->",
    re.S | re.I,
)

#: En az bir harf içermeli (sayı, para birimi, ok işareti vb. çevrilmez)
HAS_LETTER = re.compile(r"[A-Za-zÇĞİÖŞÜçğıöşü]")

#: Django sözdizimi barındıran metinler elle karar ister
HAS_DJANGO = re.compile(r"\{\{|\{%")

#: Zaten işaretli
ALREADY_MARKED = re.compile(r"\{%\s*(?:trans|translate|blocktrans)")

#: Çevrilmeyecek teknik diziler
IGNORE_EXACT = {
    "&nbsp;",
    "&times;",
    "×",
    "·",
    "—",
    "–",
    "/",
    "|",
    ":",
    "%",
    "+",
    "-",
    "OK",
    "ID",
    "PDF",
    "CSV",
    "XLSX",
    "JSON",
    "API",
    "POS",
    "KDS",
    "KOT",
    "PIN",
    "IP",
    "VIP",
    "QR",
    "SMS",
    "AI",
    "SHA-256",
}


def _placeholder_blocks(text: str) -> tuple[str, list[str]]:
    """script/style/yorum bloklarını geçici olarak çıkarır."""
    saved: list[str] = []

    def replace(match: re.Match) -> str:
        saved.append(match.group(0))
        return f"\x00BLOCK{len(saved) - 1}\x00"

    return SKIP_BLOCKS.sub(replace, text), saved


def _restore_blocks(text: str, saved: list[str]) -> str:
    for index, block in enumerate(saved):
        text = text.replace(f"\x00BLOCK{index}\x00", block)
    return text


#: Cümle ortasından kopmuş parçaların işareti
FRAGMENT_START = re.compile(r"^[,;:.)\]/|»…]")


def _is_translatable(value: str) -> bool:
    value = value.strip()
    if not value or len(value) < 2:
        return False
    if value in IGNORE_EXACT:
        return False
    if HAS_DJANGO.search(value):
        return False
    if not HAS_LETTER.search(value):
        return False
    # Yer tutucu İÇEREN metinler de reddedilir, yalnızca başlayanlar değil:
    # "... terminalden <code>git add .</code> ve ..." gibi bir cümle geri
    # yüklendiğinde HTML {% trans %} dizesinin içine düşer ve şablon bozulur.
    if "\x00BLOCK" in value:
        return False
    if FRAGMENT_START.match(value):
        return False
    # En az iki harf: "m²", "A." gibi diziler çeviri gerektirmez.
    if len(HAS_LETTER.findall(value)) < 2:
        return False
    # Yalnızca HTML varlığı (&nbsp; &gt; ...) içeren diziler
    if re.fullmatch(r"(?:&[a-zA-Z#0-9]+;|\s)+", value):
        return False
    # Ortam değişkeni / sabit adları (AI_DAILY_BUDGET_USD) çevrilmez
    if re.fullmatch(r"[A-Z0-9_]+", value):
        return False
    # Dosya yolu, komut ve URL parçaları
    if re.fullmatch(r"[\w./\\:-]+\.(py|ps1|bat|md|env|json|yml|toml|sqlite3)", value):
        return False
    return True


def _quote_safe(value: str) -> str:
    """Etiket içinde kullanılacak tırnağı seçer."""
    return "'" if '"' in value else '"'


def _attribute_quote(outer: str, value: str) -> str | None:
    """Öznitelik içindeki {% trans %} için tırnak seçer.

    Kritik: dıştaki öznitelik tırnağıyla aynı tırnak kullanılamaz.
    ``title="{% trans "metin" %}"`` HTML'i bozar — öznitelik ilk iç
    tırnakta biter ve gerisi ayrı öznitelik sanılır.
    """
    inner = "'" if outer == '"' else '"'
    if inner in value:
        # Her iki tırnak da metinde varsa güvenli bir kaçış yok; dokunma.
        return None
    return inner


def mark(text: str) -> tuple[str, set[str]]:
    """Metni işaretler; (yeni_metin, bulunan_diziler) döndürür."""
    found: set[str] = set()
    text, saved = _placeholder_blocks(text)

    # ---------- öznitelikler ----------
    def attribute_sub(match: re.Match) -> str:
        name, quote, value = match.group(1), match.group(2), match.group(3)
        if not _is_translatable(value):
            return match.group(0)
        stripped = value.strip()
        inner = _attribute_quote(quote, stripped)
        if inner is None:
            return match.group(0)
        found.add(stripped)
        return f"{name}={quote}{{% trans {inner}{stripped}{inner} %}}{quote}"

    attribute_pattern = re.compile(
        rf'\b({"|".join(ATTRIBUTES)})=(["\'])([^"\']*)\2',
        re.I,
    )
    text = attribute_pattern.sub(attribute_sub, text)

    # ---------- bir etiketin tüm içeriği ----------
    def element_sub(match: re.Match) -> str:
        opening, value, closing = match.group(0), match.group(3), match.group(4)
        # Çok satırlı metinlerde satır sonları ve girinti tek boşluğa
        # indirgenir; aksi halde kataloğa şablonun girintisi girer ve
        # boşluk düzeni değişince çeviri anahtarı tutmaz olur.
        stripped = " ".join(value.split())
        if not _is_translatable(stripped):
            return opening
        lead = value[: len(value) - len(value.lstrip())]
        trail = value[len(value.rstrip()) :]
        found.add(stripped)
        quote = _quote_safe(stripped)
        head = opening[: opening.index(">") + 1]
        return f"{head}{lead}{{% trans {quote}{stripped}{quote} %}}{trail}{closing}"

    # <etiket ...>metin</etiket>  — içerik tamamen düz metin olmalı
    element_pattern = re.compile(
        r"<([a-zA-Z][a-zA-Z0-9]*)((?:\s[^<>]*)?)>([^<>{}]+)(</\1>)",
    )
    text = element_pattern.sub(element_sub, text)

    # ---------- simgeden sonra gelen etiket metni ----------
    # Arayüzde çok yaygın kalıp: <i class="bi bi-x"></i>Kaydet
    # Bu metin bir cümle parçası değil, düğme/boş durum etiketidir.
    # Güvence: yalnızca büyük harf veya rakamla başlayan diziler alınır;
    # küçük harfle başlayanlar satır içi etiketin böldüğü cümlelerin
    # devamı olabilir ve tek başına çevrilemez.
    def icon_tail_sub(match: re.Match) -> str:
        head, value, tail = match.group(1), match.group(2), match.group(3)
        stripped = " ".join(value.split())
        if not stripped or not stripped[0].isupper() and not stripped[0].isdigit():
            return match.group(0)
        if not _is_translatable(stripped):
            return match.group(0)
        found.add(stripped)
        quote = _quote_safe(stripped)
        return f"{head}{{% trans {quote}{stripped}{quote} %}}{tail}"

    icon_tail = re.compile(r"(</i>\s*)([^<>{}]+?)(\s*</)")
    text = icon_tail.sub(icon_tail_sub, text)

    text = _restore_blocks(text, saved)
    return text, found


def ensure_i18n_load(text: str) -> str:
    """{% load i18n %} yoksa ekler."""
    if re.search(r"\{%\s*load\b[^%]*\bi18n\b", text):
        return text

    load_match = re.search(r"\{%\s*load\s+([^%]+?)\s*%\}", text)
    if load_match:
        # Mevcut load satırına ekle
        libraries = load_match.group(1).strip()
        return (
            text[: load_match.start()] + f"{{% load {libraries} i18n %}}" + text[load_match.end() :]
        )

    extends_match = re.search(r"\{%\s*extends[^%]*%\}", text)
    if extends_match:
        return text[: extends_match.end()] + "\n{% load i18n %}" + text[extends_match.end() :]

    return "{% load i18n %}\n" + text


def process(paths: list[Path], *, apply: bool) -> None:
    total_strings: set[str] = set()
    changed_files = 0
    skipped: dict[str, list[str]] = {}

    for path in paths:
        original = path.read_text(encoding="utf-8")
        marked, found = mark(original)

        if found:
            marked = ensure_i18n_load(marked)

        # Elle bakılması gerekenler: değişken içeren metin düğümleri
        manual = [
            value.strip()
            for value in re.findall(r">([^<>]*\{\{[^<>]*)<", original)
            if HAS_LETTER.search(value) and not ALREADY_MARKED.search(value)
        ]
        if manual:
            skipped[str(path.relative_to(PROJECT_ROOT))] = manual[:5]

        if marked != original:
            changed_files += 1
            total_strings |= found
            if apply:
                path.write_text(marked, encoding="utf-8", newline="\n")

    verb = "İşaretlendi" if apply else "İşaretlenecek"
    print(f"{verb}: {changed_files} şablon, {len(total_strings)} benzersiz metin")

    if not apply:
        print("\nÖrnek metinler:")
        for value in sorted(total_strings, key=str.casefold)[:30]:
            print(f"  {value[:80]}")

    print(f"\nElle bakılması gereken (değişkenli) şablon: {len(skipped)}")
    for name, values in list(skipped.items())[:10]:
        print(f"  {name}")
        for value in values[:2]:
            print(f"      {value[:70]}")


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv

    if args:
        roots = [PROJECT_ROOT / arg for arg in args]
    else:
        roots = [TEMPLATE_ROOT]

    paths: list[Path] = []
    for root in roots:
        if root.is_file():
            paths.append(root)
        else:
            paths.extend(sorted(root.rglob("*.html")))

    if not paths:
        print("Şablon bulunamadı.")
        return 1

    process(paths, apply=apply)
    return 0


if __name__ == "__main__":
    sys.exit(main())
