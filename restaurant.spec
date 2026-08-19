# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller yapılandırması — Akıllı Restaurant Yönetim Sistemi.

Kullanım:
    python -m PyInstaller restaurant.spec --noconfirm

Django'yu paketlerken üç konu özel dikkat ister:

1. **Veri dosyaları**: şablonlar, statik dosyalar ve migration'lar Python
   modülü olmadıkları için otomatik toplanmaz; açıkça eklenir.
2. **Gizli içe aktarmalar**: Django uygulamaları, veritabanı arka uçları ve
   Channels/Twisted bileşenleri dinamik olarak yüklenir; PyInstaller'ın
   statik çözümleyicisi bunları göremez.
3. **Yazılabilir veri**: veritabanı ve medya, paketin geçici açılma
   dizinine değil exe'nin yanına yazılır (bkz. config/env.py DATA_DIR).
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

PROJECT = Path(SPECPATH)

# ------------------------------------------------------------------
#  Veri dosyaları
# ------------------------------------------------------------------
datas = [
    (str(PROJECT / "templates"), "templates"),
    (str(PROJECT / "static"), "static"),
    (str(PROJECT / "staticfiles"), "staticfiles"),
    (str(PROJECT / ".env.example"), "."),
]

# Yerelleştirme dosyaları. Derlenmiş .mo dosyası olmadan İngilizce arayüz
# çalışmaz; paketlemeden önce "python scripts/i18n_tools.py compile"
# çalıştırılmalıdır (build_exe.ps1 bunu yapar).
if (PROJECT / "locale").is_dir():
    datas.append((str(PROJECT / "locale"), "locale"))

# Django'nun kendi şablon ve yerelleştirme dosyaları (admin arayüzü,
# hata sayfaları, çeviriler)
datas += collect_data_files("django", include_py_files=False)
datas += collect_data_files("rest_framework", include_py_files=False)
datas += collect_data_files("axes", include_py_files=False)

# ------------------------------------------------------------------
#  Gizli içe aktarmalar
# ------------------------------------------------------------------
hiddenimports = [
    # Veritabanı arka ucu
    "django.db.backends.sqlite3",
    "django.db.backends.sqlite3.base",
    # Şifreleme / oturum
    "django.contrib.auth.hashers",
    "django.contrib.sessions.backends.db",
    "django.contrib.staticfiles.storage",
    "whitenoise.storage",
    # ASGI / WebSocket
    "daphne",
    "daphne.server",
    "daphne.endpoints",
    "channels",
    "channels.layers",
    "channels.auth",
    "channels.routing",
    "channels.security.websocket",
    "channels.generic.websocket",
    "channels.db",
    # Raporlama
    "reportlab.pdfbase._fontdata",
    "openpyxl",
    # AI sağlayıcıları
    "httpx",
    "httpcore",
]

# Proje uygulamaları ve alt modülleri (migration'lar, sinyaller, admin)
for app in [
    "apps",
    "config",
]:
    hiddenimports += collect_submodules(app)

# Django ve üçüncü taraf uygulamalar dinamik yüklenir
for package in [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "corsheaders",
    "axes",
    "twisted",
    # WhiteNoise ara katmanı ayarlarda dize olarak referanslanır; statik
    # çözümleyici göremez.
    "whitenoise",
]:
    hiddenimports += collect_submodules(package)

hiddenimports = sorted(set(hiddenimports))

# ------------------------------------------------------------------
#  Analiz
# ------------------------------------------------------------------
a = Analysis(
    ["launcher.py"],
    pathex=[str(PROJECT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Paketi gereksiz büyüten, çalışma zamanında kullanılmayan bileşenler
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy",
        "pandas",
        "scipy",
        "IPython",
        "jupyter",
        "pytest",
        "_pytest",
        "mypy",
        "black",
        "ruff",
        "bandit",
        "pip_audit",
        "setuptools._distutils",
        # Sunum ve belge araçları yalnızca geliştirme tarafındadır
        # (scripts/make_presentation.py). lxml, python-pptx'in
        # bağımlılığıdır ve pakete girerse ~4 MB gereksiz yer kaplar.
        "pptx",
        "pypdf",
        "lxml",
        # autobahn'ın NVX hızlandırıcısı: derlenmiş uzantı çalışma anında
        # ".c" kaynağını da arar. Paketten çıkarılınca autobahn saf Python
        # karşılığına düşer (bkz. launcher.py AUTOBAHN_USE_NVX).
        "_nvx_utf8validator",
        "_nvx_xormasker",
        "autobahn.nvx",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Akilli Restaurant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX bazı virüs tarayıcılarında yanlış alarm üretir
    runtime_tmpdir=None,
    console=True,  # sunucu durumu ve Ctrl+C için konsol gerekli
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(PROJECT / "assets" / "restaurant.ico"),
)
