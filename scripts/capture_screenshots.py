"""Tanıtım sunumu için uygulama ekran görüntülerini üretir.

SENTETİK demo veriyle (``seed_demo``) çalışan bir sunucudan ana ekranların
görüntülerini alır ve ``sunum/screenshots/{tr,en}/`` altına yazar.

Gizlilik kuralları (bu script bunları zorlar, umut etmez)
---------------------------------------------------------
1. **Kimlik bilgisi kaynak kodda tutulmaz.** Görüntü alan hesabın parolası
   her çalıştırmada bellekte rastgele üretilir; hiçbir dosyaya yazılmaz.
2. **Kişisel veriye erişimi olmayan bir rol kullanılır.** Hesap
   ``customer.pii`` iznini AÇIKÇA REDDEDER (``denied_permissions``), bu
   yüzden telefon/e-posta maskeli, alerji (sağlık) notu gizli görünür.
   Reddedilen izin, rol matrisini de ezer (bkz. ``User.has_perm_code``).
3. **Parola alanı içeren ekran görüntüsü alınmaz.** Giriş ekranı listede
   yoktur ve oturum açıldıktan sonra görüntü alınır.
4. Görüntü alınmadan önce sayfadaki tüm parola alanları ve varsa gizli
   değer kalıntıları DOM'dan kaldırılır (son kontrol).
5. Görüntü alan hesap iş bittiğinde devre dışı bırakılır.

Gerçek işletme verisi İÇERMEZ: script ``RESTAURANT_DATA_DIR`` ile izole
edilmiş geçici bir veritabanına karşı çalıştırılmalıdır.

Kullanım (önerilen akış):
    $env:RESTAURANT_DATA_DIR = "<geçici klasör>"
    python manage.py migrate
    python manage.py seed_demo
    python manage.py runserver 127.0.0.1:8321   # ayrı pencerede
    python scripts/capture_screenshots.py --base-url http://127.0.0.1:8321

Gereksinim: pip install playwright && playwright install chromium
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "sunum" / "screenshots"

#: Görüntü alan hesabın kullanıcı adı. Parolası çalıştırma anında üretilir.
CAPTURE_USER = "tanitim"

#: Bu hesaba kapatılan izinler. Kişisel/sağlık verisi ve tehlikeli alanlar.
CAPTURE_DENIED_PERMISSIONS = [
    "customer.pii",  # telefon/e-posta/alerji notu maskeli kalsın
    "data.erase",
    "backup.download",
    "backup.restore",
    "devcenter.terminal",
    "devcenter.apply",
    "user.manage",
]

#: (url adı, dosya adı, sayfa yüklendikten sonra ek bekleme sn)
PAGES: list[tuple[str, str, float]] = [
    ("reports:dashboard", "01_panel", 1.5),  # Chart.js animasyonları
    ("orders:pos", "02_pos", 1.0),
    ("kitchen:display", "03_mutfak_kds", 1.0),
    ("floor:table_map", "04_salon", 1.0),
    ("inventory:ingredient_list", "05_stok", 0.5),
    ("catalog:product_list", "06_menu", 0.5),
    ("crm:customer_list", "07_musteri", 0.5),
    ("floor:reservation_list", "08_rezervasyon", 0.5),
    ("reports:statistics", "09_istatistik", 1.5),
    ("ai:assistant", "10_ai_asistan", 0.5),
]

#: Görüntü alınmadan önce DOM'dan temizlenecekler (son güvenlik ağı).
SCRUB_JS = """
() => {
  // 1) Parola alanları hiçbir görüntüde bulunmamalı.
  document.querySelectorAll('input[type="password"]').forEach(el => el.remove());
  // 2) Anahtar/parola benzeri metin kalıntıları maskelensin.
  const patterns = [
    /(sk-[A-Za-z0-9_\\-]{8,})/g,
    /(nvapi-[A-Za-z0-9_\\-]{8,})/g,
    /(AIza[A-Za-z0-9_\\-]{8,})/g,
    /(gh[pousr]_[A-Za-z0-9]{8,})/g,
  ];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    let text = node.nodeValue;
    for (const re of patterns) text = text.replace(re, '••••••••');
    if (text !== node.nodeValue) node.nodeValue = text;
  }
}
"""


def _random_password() -> str:
    """Yalnızca bu çalıştırma için geçerli, güçlü, tek kullanımlık parola."""
    alphabet = string.ascii_letters + string.digits
    return "Capture-" + "".join(secrets.choice(alphabet) for _ in range(16))


def _setup_django() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    # Playwright sync API bir event-loop greenlet'i içinde çalışır; Django
    # ORM çağrıları (dil değiştirme) bu bağlamda async sanılır. Bu bir
    # tek-kullanıcılı yardımcı script olduğu için güvenli.
    os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")
    sys.path.insert(0, str(PROJECT_ROOT))
    import django

    django.setup()


def _ensure_capture_user(password: str) -> None:
    """Kişisel veriye erişimi olmayan, tek kullanımlık görüntü hesabı kurar.

    Rol olarak restoran müdürü seçilir (tüm ekranlar açılsın), ancak
    ``customer.pii`` ve diğer hassas izinler açıkça REDDEDİLİR. Reddedilen
    izin rol matrisini ezdiği için hesap, rolüne rağmen maskesiz kişisel
    veri göremez.
    """
    from django.contrib.auth import get_user_model

    from apps.accounts.permissions import Role

    User = get_user_model()
    user, _created = User.objects.get_or_create(
        username=CAPTURE_USER,
        defaults={
            "first_name": "Tanıtım",
            "last_name": "Hesabı",
            "role": Role.RESTAURANT_MANAGER,
        },
    )
    user.role = Role.RESTAURANT_MANAGER
    user.is_active = True
    user.is_superuser = False  # süper kullanıcı tüm izinleri geçersiz kılar
    user.is_staff = False
    user.must_change_password = False
    user.denied_permissions = list(CAPTURE_DENIED_PERMISSIONS)
    user.extra_permissions = ["report.statistics", "ai.use", "inventory.view"]
    user.set_password(password)
    user.set_pin(None)
    user.save()

    if user.has_perm_code("customer.pii"):  # pragma: no cover - savunma kontrolü
        raise SystemExit(
            "GÜVENLİK: görüntü hesabı 'customer.pii' iznine sahip; ekran " "görüntüsü alınmadı."
        )


def _disable_capture_user() -> None:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    User.objects.filter(username=CAPTURE_USER).update(is_active=False)


def _resolve_pages() -> list[tuple[str, str, float]]:
    """URL adlarını yola çevirir; çözülemeyenleri uyarıyla atlar."""
    from django.urls import NoReverseMatch, reverse

    resolved = []
    for name, filename, extra_wait in PAGES:
        try:
            resolved.append((reverse(name), filename, extra_wait))
        except NoReverseMatch:
            print(f"  [!] Atlandı (URL adı yok): {name}")
    return resolved


def _set_demo_language(code: str) -> None:
    from django.contrib.auth import get_user_model

    user = get_user_model().objects.get(username=CAPTURE_USER)
    user.language_preference = code
    user.save(update_fields=["language_preference"])


def capture(base_url: str, languages: list[str], password: str) -> int:
    # Django (daphne/twisted) Windows'ta selector event-loop politikası
    # kurar; Playwright'ın tarayıcı süreci başlatabilmesi için Proactor
    # politikası gerekir.
    if sys.platform == "win32":
        import asyncio

        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    from playwright.sync_api import sync_playwright

    pages = _resolve_pages()
    total = 0
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1600, "height": 900}, device_scale_factor=1.5
        )
        page = context.new_page()

        # Giriş. Giriş ekranının kendisi ASLA kaydedilmez (parola alanı içerir).
        page.goto(f"{base_url}/accounts/login/", wait_until="networkidle")
        page.fill('input[name="username"]', CAPTURE_USER)
        page.fill('input[name="password"]', password)
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        for lang in languages:
            _set_demo_language(lang)
            out_dir = OUTPUT_DIR / lang
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"--- Dil: {lang} -> {out_dir}")
            for path, filename, extra_wait in pages:
                target = f"{base_url}{path}"
                try:
                    page.goto(target, wait_until="networkidle")
                    time.sleep(extra_wait)
                    page.evaluate(SCRUB_JS)
                    page.screenshot(path=str(out_dir / f"{filename}.png"), full_page=False)
                    print(f"  [ok] {filename}  ({path})")
                    total += 1
                except Exception as exc:  # tek sayfa hatası akışı durdurmasın
                    print(f"  [!] {filename}: {exc}")
        browser.close()
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8321")
    parser.add_argument("--languages", default="tr,en", help="Virgüllü dil listesi (tr,en)")
    parser.add_argument(
        "--keep-user",
        action="store_true",
        help="İş bitince görüntü hesabını devre dışı bırakma (hata ayıklama).",
    )
    args = parser.parse_args()

    _setup_django()
    password = _random_password()  # yalnızca bellekte; hiçbir dosyaya yazılmaz
    _ensure_capture_user(password)
    languages = [code.strip() for code in args.languages.split(",") if code.strip()]
    try:
        total = capture(args.base_url.rstrip("/"), languages, password)
    finally:
        if not args.keep_user:
            _disable_capture_user()
    print(f"Toplam {total} ekran görüntüsü alındı -> {OUTPUT_DIR}")
    return 0 if total else 1


if __name__ == "__main__":
    sys.exit(main())
