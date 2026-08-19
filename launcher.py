"""Paketlenmiş uygulamanın giriş noktası (PyInstaller).

Bu dosya yalnızca `.exe` içinde çalışır. Görevleri:

1. Yazılabilir veri dizinini hazırlar (exe'nin yanı)
2. İlk çalıştırmada veritabanını oluşturur ve ilk kurulum sihirbazını sunar
3. ASGI sunucusunu (Daphne) başlatır — mutfak ekranının WebSocket'i için
4. Tarayıcıyı açar
5. Konsolda anlaşılır durum bilgisi gösterir

Geliştirme sırasında bu dosyaya gerek yoktur; `manage.py runserver` kullanın.
"""

from __future__ import annotations

import os
import socket
import sys
import threading
import time
import webbrowser

# autobahn'ın NVX hızlandırıcısı, derlenmiş uzantının yanında ".c" kaynak
# dosyasını da çalışma anında okumaya çalışır; bu dosya pakete girmediği
# için paketlenmiş uygulamada FileNotFoundError verir. Autobahn'ın
# belgelenmiş anahtarıyla saf Python karşılığına geçiyoruz — tek bir
# restoran ölçeğinde performans farkı hissedilmez.
# Bu satır, autobahn ilk kez içe aktarılmadan ÖNCE çalışmalıdır.
os.environ.setdefault("AUTOBAHN_USE_NVX", "0")

APP_NAME = "Akıllı Restaurant Yönetim Sistemi"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000


# ------------------------------------------------------------------
#  Konsol yardımcıları
# ------------------------------------------------------------------
def _make_console_tolerant() -> None:
    """Konsolun kodlayamadığı bir karakter uygulamayı düşürmesin.

    Windows konsolu Türkçe sistemlerde cp1254/cp857 kullanır. Bir çıktı
    metni bu tabloda olmayan bir işaret içerirse (örneğin bir onay simgesi)
    Python ``UnicodeEncodeError`` yükseltir; standart çıktıya yazan her yer
    buna karşı savunmasız olduğu için bu, kurulum sırasında uygulamanın
    tamamen kapanmasına yol açabilir.

    Kodlamayı değiştirmiyoruz — değiştirseydik Türkçe harfler bozulurdu.
    Yalnızca hata davranışını "yerine soru işareti koy"a çekiyoruz.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # type: ignore[union-attr]
        except (AttributeError, ValueError, OSError):
            pass


_make_console_tolerant()


def _supports_unicode() -> bool:
    try:
        "─".encode(sys.stdout.encoding or "utf-8")
        return True
    except (UnicodeEncodeError, LookupError, TypeError):
        return False


BOX = "═" if _supports_unicode() else "="


def banner(text: str) -> None:
    line = BOX * 62
    print()
    print(f"  {line}")
    print(f"    {text}")
    print(f"  {line}")
    print()


def step(text: str) -> None:
    print(f"  [*] {text}")


def ok(text: str) -> None:
    print(f"  [OK] {text}")


def warn(text: str) -> None:
    print(f"  [!]  {text}")


def fail(text: str) -> None:
    print(f"  [X]  {text}")


# ------------------------------------------------------------------
#  Ağ
# ------------------------------------------------------------------
def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(1.0)
        return sock.connect_ex((host, port)) == 0


def find_free_port(host: str, start: int, attempts: int = 20) -> int | None:
    for offset in range(attempts):
        candidate = start + offset
        if not port_in_use(host, candidate):
            return candidate
    return None


def is_our_app(host: str, port: int) -> bool:
    """Porttaki sunucu bu uygulama mı?

    Port dolu olması tek başına "program zaten açık" anlamına gelmez;
    bambaşka bir yazılım da o portu kullanıyor olabilir. Sağlık uç
    noktasına bakarak emin oluruz.
    """
    import json
    import urllib.error
    import urllib.request

    try:
        with urllib.request.urlopen(  # noqa: S310 - sabit, yerel adres
            f"http://{host}:{port}/healthz/", timeout=2
        ) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return "status" in payload and "database" in payload
    except (urllib.error.URLError, OSError, ValueError, json.JSONDecodeError):
        return False


def open_browser_when_ready(url: str, host: str, port: int) -> None:
    """Sunucu gerçekten yanıt vermeye başlayınca tarayıcıyı açar."""
    for _ in range(60):
        time.sleep(0.5)
        if port_in_use(host, port):
            time.sleep(0.8)  # ilk isteğin hazır olması için kısa pay
            try:
                webbrowser.open(url)
            except Exception:
                warn(f"Tarayıcı açılamadı. Elle açın: {url}")
            return


# ------------------------------------------------------------------
#  Django kurulumu
# ------------------------------------------------------------------
def prepare_database() -> tuple[bool, int]:
    """Veritabanını hazırlar. (yeni_kurulum_mu, kullanıcı_sayısı) döndürür."""
    from django.contrib.auth import get_user_model
    from django.core.management import call_command
    from django.db import connection

    tables_before = set(connection.introspection.table_names())
    is_new = "django_migrations" not in tables_before

    step("Veritabanı hazırlanıyor...")
    call_command("migrate", interactive=False, verbosity=0)
    ok("Veritabanı hazır")

    user_count = get_user_model().objects.count()
    return is_new, user_count


def first_run_wizard() -> None:
    """Hiç kullanıcı yokken çalışan basit kurulum sihirbazı."""
    from django.contrib.auth import get_user_model
    from django.core.management import call_command

    print()
    warn("Sistemde henüz kullanıcı yok — giriş yapamazsınız.")
    print()
    print("      1) Örnek veriyle dene (menü, stok, 30 günlük satış geçmişi)")
    print("      2) Boş başla, yalnızca yönetici hesabı oluştur")
    print("      3) Atla (daha sonra kurarım)")
    print()

    try:
        choice = input("  Seçiminiz [1/2/3] (varsayılan 1): ").strip() or "1"
    except (EOFError, KeyboardInterrupt):
        choice = "3"

    if choice == "1":
        step("Örnek veri yükleniyor, bu biraz sürebilir...")
        # `seed_demo` her çalıştırmada rastgele bir demo parolası üretir ve
        # kendi çıktısında bir kez gösterir. Parolayı burada tekrarlamayız:
        # sabit bir demo parolası hiçbir yerde belgelenmez.
        call_command("seed_demo", verbosity=1)
        print()
        ok("Örnek veri hazır. Giriş bilgileri yukarıda BİR KEZ gösterildi — not alın.")
        warn("Örnek verilerin tamamı sentetiktir; gerçek kullanıma geçmeden önce temizleyin.")
    elif choice == "2":
        User = get_user_model()
        print()
        print("  Yönetici hesabı oluşturuluyor.")
        print("  (Parola en az 10 karakter olmalı, harf ve rakam içermeli.)")
        print()
        while True:
            try:
                username = input("  Kullanıcı adı: ").strip()
                if not username:
                    continue
                if User.objects.filter(username__iexact=username).exists():
                    fail("Bu kullanıcı adı zaten var.")
                    continue
                import getpass

                password = getpass.getpass("  Parola: ")
                confirm = getpass.getpass("  Parola (tekrar): ")
                if password != confirm:
                    fail("Parolalar eşleşmiyor.")
                    continue

                from django.contrib.auth.password_validation import validate_password
                from django.core.exceptions import ValidationError

                try:
                    validate_password(password)
                except ValidationError as exc:
                    for message in exc.messages:
                        fail(message)
                    continue

                from apps.accounts.permissions import Role

                User.objects.create_superuser(
                    username=username, email="", password=password, role=Role.OWNER
                )
                print()
                ok(f"Yönetici hesabı oluşturuldu: {username}")
                break
            except (EOFError, KeyboardInterrupt):
                print()
                warn("Atlandı.")
                break
    else:
        warn("Atlandı. Kullanıcı oluşturmadan giriş yapamazsınız.")


# ------------------------------------------------------------------
#  Sunucu
# ------------------------------------------------------------------
def run_server(host: str, port: int) -> None:
    """Daphne (ASGI) ile sunucuyu başlatır.

    Daphne tercih edilir çünkü mutfak ekranının canlı akışı WebSocket
    kullanır; WSGI sunucusu bunu desteklemez.
    """
    from daphne.endpoints import build_endpoint_description_strings
    from daphne.server import Server

    from config.asgi import application

    endpoints = build_endpoint_description_strings(host=host, port=port)
    Server(
        application=application,
        endpoints=endpoints,
        signal_handlers=True,
        verbosity=0,
    ).run()


# ------------------------------------------------------------------
#  Ana akış
# ------------------------------------------------------------------
def main() -> int:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    # Paketlenmiş uygulama üretim gibi davranır: hata ayıklama kapalı.
    os.environ.setdefault("DJANGO_DEBUG", "False")
    os.environ.setdefault("DJANGO_ENV", "production")

    banner(APP_NAME)

    import django

    from config.env import DATA_DIR

    print(f"  Veri klasörü : {DATA_DIR}")

    # İlk çalıştırmada .env oluştur ki kullanıcı ayarları düzenleyebilsin
    env_file = DATA_DIR / ".env"
    if not env_file.exists():
        from config.env import BASE_DIR

        sample = BASE_DIR / ".env.example"
        if sample.is_file():
            from django.core.management.utils import get_random_secret_key

            content = sample.read_text(encoding="utf-8")
            content = content.replace(
                "DJANGO_SECRET_KEY=degistir-bu-anahtari-uretimde",
                f"DJANGO_SECRET_KEY={get_random_secret_key()}",
            )
            content = content.replace("DJANGO_DEBUG=True", "DJANGO_DEBUG=False")
            content = content.replace("DJANGO_ENV=development", "DJANGO_ENV=production")
            env_file.write_text(content, encoding="utf-8")
            ok(f"Ayar dosyası oluşturuldu: {env_file.name}")
            # Yeni üretilen anahtarı bu çalıştırmada da kullan
            from dotenv import load_dotenv

            load_dotenv(env_file, override=True)

    django.setup()

    # ---------- veritabanı ----------
    try:
        _is_new, user_count = prepare_database()
    except Exception as exc:  # pragma: no cover
        fail(f"Veritabanı hazırlanamadı: {exc}")
        print()
        print(f"  Ayrıntı için: {DATA_DIR / 'logs' / 'restaurant.log'}")
        input("  Kapatmak için Enter'a basın...")
        return 1

    if user_count == 0:
        first_run_wizard()

    # ---------- port ----------
    host = os.environ.get("RESTAURANT_HOST", DEFAULT_HOST)
    port = int(os.environ.get("RESTAURANT_PORT", DEFAULT_PORT))

    if port_in_use(host, port):
        if is_our_app(host, port):
            url = f"http://{host}:{port}"
            ok("Program zaten çalışıyor.")
            print(f"       Tarayıcı açılıyor: {url}")
            webbrowser.open(url)
            time.sleep(2)
            return 0

        # Portu başka bir yazılım tutuyor; ona tarayıcı açmak yanlış olur.
        warn(f"{port} portunu başka bir program kullanıyor.")
        free = find_free_port(host, port + 1)
        if free is None:
            fail("Boş port bulunamadı.")
            input("  Kapatmak için Enter'a basın...")
            return 1
        port = free
        print(f"       Bunun yerine {port} portu kullanılacak.")

    url = f"http://{host}:{port}"

    print()
    ok("Sunucu başlatılıyor")
    print()
    print(f"      Adres  : {url}")
    print("      Durdur : Bu pencerede Ctrl+C  (veya pencereyi kapatın)")
    print()
    print(f"  {'-' * 60}")
    print()

    threading.Thread(target=open_browser_when_ready, args=(url, host, port), daemon=True).start()

    try:
        run_server(host, port)
    except KeyboardInterrupt:
        pass
    except Exception as exc:  # pragma: no cover
        print()
        fail(f"Sunucu hatası: {exc}")
        input("  Kapatmak için Enter'a basın...")
        return 1

    print()
    print("  Sunucu durduruldu.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
