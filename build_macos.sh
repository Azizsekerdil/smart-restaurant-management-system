#!/usr/bin/env bash
# macOS paketi üretir — Akıllı Restaurant Yönetim Sistemi.
#
# Sunucu/konsol uygulaması olduğu için --onedir kullanılır ve --windowed
# KULLANILMAZ: ilk kurulum sihirbazı (launcher.py) konsoldan girdi ister.
#
# NOT: macOS'un sistem bash'i 3.2'dir; "set -u" boş dizi açılımını
# ("${ARR[@]}") hata saydığı için bilerek kullanılmıyor.
set -eo pipefail

cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "HATA: macOS paketi bir Mac üzerinde oluşturulmalıdır."
  exit 1
fi

APP_NAME="Akilli Restaurant"
PYTHON_BIN="${PYTHON_BIN:-python3}"

"$PYTHON_BIN" -m pip install --upgrade pip
"$PYTHON_BIN" -m pip install -r requirements.txt
"$PYTHON_BIN" -m pip install pyinstaller

rm -rf build/macos "dist/$APP_NAME" "dist/$APP_NAME-macOS.zip"
mkdir -p build/macos

# ---------- 1) Çeviri kataloğu (saf Python, gettext gerekmez) ----------
"$PYTHON_BIN" scripts/i18n_tools.py compile
if [[ ! -f locale/en/LC_MESSAGES/django.mo ]]; then
  echo "HATA: django.mo üretilmedi; İngilizce arayüz çalışmaz."
  exit 1
fi

# ---------- 2) Statik dosyalar (üretim ayarlarıyla) ----------
# KRİTİK: DEBUG=False olmalı. WhiteNoise ancak o zaman hash'li dosya
# adları ve staticfiles.json manifestosunu üretir; manifest paket dışı
# kalırsa uygulama her sayfada 500 hatası verir (bkz. scripts/build_exe.ps1).
DJANGO_DEBUG=False DJANGO_ENV=production \
  DJANGO_SECRET_KEY="build-time-only-not-a-real-secret" \
  "$PYTHON_BIN" manage.py collectstatic --noinput --clear
if [[ ! -f staticfiles/staticfiles.json ]]; then
  echo "HATA: staticfiles.json üretilmedi; statik dosyalar sunulamaz."
  exit 1
fi

# ---------- 3) PyInstaller ----------
# restaurant.spec Windows'a özgü .ico kullandığı için macOS'ta eşdeğeri
# CLI bayraklarıyla kurulur (aşağıdaki listeler spec'ten birebir alınmıştır).
# İkon png'si yoksa .icns üretilmez; konsol uygulamasında .app paketi
# olmadığından ikon zaten görünmez.
#
# --add-data yolları MUTLAK olmalı: --specpath kullanıldığı için göreli
# yollar spec klasörüne göre çözülür ve bulunamaz.
DATA_ARGS=(
  --add-data "$PROJECT_ROOT/templates:templates"
  --add-data "$PROJECT_ROOT/static:static"
  --add-data "$PROJECT_ROOT/staticfiles:staticfiles"
  --add-data "$PROJECT_ROOT/.env.example:."
)
[[ -d locale ]] && DATA_ARGS+=(--add-data "$PROJECT_ROOT/locale:locale")

"$PYTHON_BIN" -m PyInstaller --noconfirm --clean --onedir \
  --workpath build/macos/pyinstaller --specpath build/macos \
  --name "$APP_NAME" \
  --paths "$PROJECT_ROOT" \
  "${DATA_ARGS[@]}" \
  --collect-data django --collect-data rest_framework --collect-data axes \
  --collect-submodules apps --collect-submodules config \
  --collect-submodules django.contrib.admin \
  --collect-submodules django.contrib.auth \
  --collect-submodules django.contrib.contenttypes \
  --collect-submodules django.contrib.sessions \
  --collect-submodules django.contrib.messages \
  --collect-submodules django.contrib.staticfiles \
  --collect-submodules django.contrib.humanize \
  --collect-submodules rest_framework \
  --collect-submodules rest_framework_simplejwt \
  --collect-submodules django_filters \
  --collect-submodules corsheaders \
  --collect-submodules axes \
  --collect-submodules twisted \
  --collect-submodules whitenoise \
  --hidden-import django.db.backends.sqlite3 \
  --hidden-import django.db.backends.sqlite3.base \
  --hidden-import django.contrib.auth.hashers \
  --hidden-import django.contrib.sessions.backends.db \
  --hidden-import django.contrib.staticfiles.storage \
  --hidden-import whitenoise.storage \
  --hidden-import daphne --hidden-import daphne.server \
  --hidden-import daphne.endpoints \
  --hidden-import channels --hidden-import channels.layers \
  --hidden-import channels.auth --hidden-import channels.routing \
  --hidden-import channels.security.websocket \
  --hidden-import channels.generic.websocket --hidden-import channels.db \
  --hidden-import reportlab.pdfbase._fontdata --hidden-import openpyxl \
  --hidden-import httpx --hidden-import httpcore \
  --exclude-module tkinter --exclude-module matplotlib \
  --exclude-module numpy --exclude-module pandas --exclude-module scipy \
  --exclude-module IPython --exclude-module jupyter \
  --exclude-module pytest --exclude-module _pytest --exclude-module mypy \
  --exclude-module black --exclude-module ruff --exclude-module bandit \
  --exclude-module pip_audit --exclude-module setuptools._distutils \
  --exclude-module pptx --exclude-module pypdf --exclude-module lxml \
  --exclude-module _nvx_utf8validator --exclude-module _nvx_xormasker \
  --exclude-module autobahn.nvx \
  "$PROJECT_ROOT/launcher.py"

OUT_DIR="dist/$APP_NAME"
[[ -d "$OUT_DIR" ]] || { echo "HATA: $OUT_DIR oluşturulamadı."; exit 1; }
[[ -x "$OUT_DIR/$APP_NAME" ]] || { echo "HATA: $OUT_DIR/$APP_NAME çalıştırılabilir değil."; exit 1; }

ditto -c -k --keepParent "$OUT_DIR" "dist/$APP_NAME-macOS.zip"
echo "Tamamlandı: $OUT_DIR"
echo "Dağıtım ZIP'i: dist/$APP_NAME-macOS.zip"
