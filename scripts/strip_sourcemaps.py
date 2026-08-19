"""Vendor dosyalarındaki kaynak harita (source map) referanslarını temizler.

Neden gerekli:
    Küçültülmüş (minified) CSS/JS dosyaları sonunda
    ``/*# sourceMappingURL=dosya.map */`` yorumu taşır. Bu yorum yalnızca
    tarayıcı geliştirici araçları içindir. Biz ``.map`` dosyalarını depoya
    almıyoruz (her biri birkaç yüz KB ve son kullanıcıya faydası yok).

    Django'nun manifest tabanlı statik depolaması ise CSS içindeki tüm
    referansları çözmeye çalışır ve eksik ``.map`` dosyasında toplama
    işlemini hataya düşürür.

Kullanım:
    python scripts/strip_sourcemaps.py

Dosyaların içeriği bunun dışında değiştirilmez; lisans başlıkları korunur
(bkz. THIRD_PARTY_NOTICES.md).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = PROJECT_ROOT / "static" / "vendor"

# CSS: /*# sourceMappingURL=... */    JS: //# sourceMappingURL=...
PATTERN = re.compile(
    r"(?:/\*#\s*sourceMappingURL=[^*]*\*/|//#\s*sourceMappingURL=\S*)\s*$",
    re.MULTILINE,
)


def main() -> int:
    if not VENDOR_DIR.is_dir():
        print(f"Vendor klasörü bulunamadı: {VENDOR_DIR}")
        return 1

    cleaned = 0
    for path in sorted(VENDOR_DIR.rglob("*")):
        if path.suffix not in {".css", ".js"} or not path.is_file():
            continue
        original = path.read_text(encoding="utf-8")
        stripped = PATTERN.sub("", original).rstrip() + "\n"
        if stripped != original:
            path.write_text(stripped, encoding="utf-8")
            print(f"  temizlendi: {path.relative_to(PROJECT_ROOT)}")
            cleaned += 1

    print(f"\n{cleaned} dosya güncellendi." if cleaned else "\nTemizlenecek dosya yok.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
