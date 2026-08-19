<#
.SYNOPSIS
    Akıllı Restaurant Yönetim Sistemi — Windows kurulum sihirbazı.

.DESCRIPTION
    Sanal ortam oluşturur, bağımlılıkları yükler, .env dosyasını hazırlar,
    veritabanını kurar, yönetici hesabı açar ve isteğe bağlı demo veriyi yükler.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1

.EXAMPLE
    # Soru sormadan, demo veriyle birlikte kur
    powershell -ExecutionPolicy Bypass -File .\setup_windows.ps1 -Unattended -WithDemo
#>

[CmdletBinding()]
param(
    [switch]$Unattended,   # Soru sorma
    [switch]$WithDemo,     # Demo veriyi yükle
    [switch]$Dev           # Geliştirme bağımlılıklarını da kur
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

function Write-Step($Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}
function Write-Ok($Message)   { Write-Host "    [OK] $Message" -ForegroundColor Green }
function Write-Warn($Message) { Write-Host "    [!]  $Message" -ForegroundColor Yellow }
function Write-Err($Message)  { Write-Host "    [X]  $Message" -ForegroundColor Red }

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Blue
Write-Host "    AKILLI RESTAURANT YONETIM SISTEMI - Kurulum" -ForegroundColor Blue
Write-Host "  ============================================================" -ForegroundColor Blue
Write-Host "    Proje klasoru: $ProjectRoot"

# ------------------------------------------------------------------ 1) Python
Write-Step "Python surumu kontrol ediliyor"
try {
    $pythonVersion = (python --version 2>&1) -replace "Python ", ""
} catch {
    Write-Err "Python bulunamadi."
    Write-Host "    https://www.python.org/downloads/windows/ adresinden Python 3.12 kurun."
    Write-Host "    Kurulum sirasinda 'Add python.exe to PATH' kutusunu isaretleyin."
    exit 1
}

$versionParts = $pythonVersion.Split(".")
$major = [int]$versionParts[0]
$minor = [int]$versionParts[1]

if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 11)) {
    Write-Err "Python $pythonVersion bulundu; en az 3.11 gerekiyor."
    exit 1
}
if ($major -eq 3 -and $minor -ge 13) {
    Write-Warn "Python $pythonVersion kullaniyorsunuz. Bazi paketlerin hazir surumu"
    Write-Warn "olmayabilir. Sorun yasarsaniz Python 3.12 onerilir."
} else {
    Write-Ok "Python $pythonVersion"
}

# ------------------------------------------------------------------ 2) venv
Write-Step "Sanal ortam hazirlaniyor"
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $venvPython) {
    Write-Ok "Mevcut sanal ortam kullanilacak (.venv)"
} else {
    python -m venv .venv
    if (-not (Test-Path $venvPython)) { Write-Err "Sanal ortam olusturulamadi."; exit 1 }
    Write-Ok "Sanal ortam olusturuldu (.venv)"
}

# ------------------------------------------------------------------ 3) paketler
Write-Step "Bagimliliklar yukleniyor (birkac dakika surebilir)"
& $venvPython -m pip install --upgrade pip --quiet
$requirementsFile = if ($Dev) { "requirements-dev.txt" } else { "requirements.txt" }
& $venvPython -m pip install -r $requirementsFile --quiet
if ($LASTEXITCODE -ne 0) { Write-Err "Paket kurulumu basarisiz."; exit 1 }
Write-Ok "$requirementsFile yuklendi"

# ------------------------------------------------------------------ 4) .env
Write-Step "Ortam dosyasi (.env) hazirlaniyor"
if (Test-Path ".env") {
    Write-Ok "Mevcut .env korunuyor"
} else {
    Copy-Item ".env.example" ".env"

    # Guvenli bir gizli anahtar uret ve yaz
    $secretKey = & $venvPython -c "from django.core.management.utils import get_random_secret_key as k; print(k())"
    $content = Get-Content ".env" -Raw
    $content = $content -replace "DJANGO_SECRET_KEY=.*", "DJANGO_SECRET_KEY=$secretKey"
    $content = $content -replace "DEVCENTER_ROOT=.*", "DEVCENTER_ROOT=$ProjectRoot"
    Set-Content ".env" $content -Encoding UTF8 -NoNewline

    Write-Ok ".env olusturuldu ve guvenli DJANGO_SECRET_KEY uretildi"
    Write-Warn "API anahtarlarinizi eklemek icin .env dosyasini duzenleyin."
}

# ------------------------------------------------------------------ 5) klasorler
Write-Step "Klasorler hazirlaniyor"
foreach ($dir in @("logs", "media", "backups", "staticfiles")) {
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
}
Write-Ok "logs, media, backups, staticfiles"

# ------------------------------------------------------------------ 6) veritabani
Write-Step "Veritabani hazirlaniyor"
& $venvPython manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { Write-Err "Veritabani olusturulamadi."; exit 1 }
Write-Ok "Tablolar olusturuldu"

# ------------------------------------------------------------------ 7) statik
Write-Step "Statik dosyalar toplaniyor"
& $venvPython manage.py collectstatic --noinput --clear | Out-Null
Write-Ok "Statik dosyalar hazir"

# ------------------------------------------------------------------ 8) yonetici
Write-Step "Yonetici hesabi"
$userCount = & $venvPython -c @"
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
django.setup()
from django.contrib.auth import get_user_model
print(get_user_model().objects.count())
"@ 2>$null

if ([int]$userCount -gt 0) {
    Write-Ok "Sistemde zaten $userCount kullanici var; olusturma atlandi"
} elseif ($Unattended) {
    Write-Warn "Gozetimsiz mod: yonetici olusturulmadi."
    Write-Warn "Daha sonra calistirin:  python manage.py createsuperuser"
} else {
    Write-Host "    Yonetici hesabi olusturulacak. Kullanici adi, e-posta ve parola girin."
    Write-Host "    (Parola en az 10 karakter olmali ve harf + rakam icermeli.)"
    Write-Host ""
    & $venvPython manage.py createsuperuser
    if ($LASTEXITCODE -eq 0) { Write-Ok "Yonetici hesabi olusturuldu" }
}

# ------------------------------------------------------------------ 9) demo
Write-Step "Demo verisi"
$loadDemo = $WithDemo
if (-not $Unattended -and -not $WithDemo) {
    $answer = Read-Host "    Ornek veri yuklensin mi? (menu, stok, 30 gunluk satis) [E/h]"
    $loadDemo = ($answer -eq "" -or $answer -match "^[eEyY]")
}
if ($loadDemo) {
    & $venvPython manage.py seed_demo
    Write-Ok "Demo verisi yuklendi"
    Write-Warn "Demo hesaplari yalnizca deneme icindir."
    Write-Warn "Gercek kullanimdan once:  python manage.py seed_demo --reset"
} else {
    Write-Ok "Demo verisi atlandi"
}

# ------------------------------------------------------------------ 10) LM Studio
Write-Step "Yerel yapay zeka (LM Studio) kontrol ediliyor"
try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:1234/v1/models" -TimeoutSec 5
    Write-Ok "LM Studio calisiyor - $($models.data.Count) model yuklu"
    foreach ($m in $models.data | Select-Object -First 6) {
        Write-Host "         - $($m.id)"
    }
} catch {
    Write-Warn "LM Studio erisilemedi (http://127.0.0.1:1234)."
    Write-Host "         Yapay zeka OZELLIKLERI ISTEGE BAGLIDIR - sistem onsuz de calisir."
    Write-Host "         Etkinlestirmek icin:"
    Write-Host "           1. lmstudio.ai adresinden LM Studio'yu kurun"
    Write-Host "           2. Discover sekmesinden bir model indirin"
    Write-Host "           3. Developer sekmesi -> Start Server"
    Write-Host "           4. python manage.py ai_check --provider lmstudio"
}

# ------------------------------------------------------------------ ozet
Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "    KURULUM TAMAMLANDI" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Uygulamayi baslatmak icin:" -ForegroundColor White
Write-Host "      .\run_app.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Gelistirici modu:" -ForegroundColor White
Write-Host "      .\run_dev.ps1" -ForegroundColor Yellow
Write-Host ""
Write-Host "  Adres:  http://127.0.0.1:8000"
Write-Host ""
if ($loadDemo) {
    # Sabit bir demo parolasi belgelenmez: seed_demo her calistirmada
    # rastgele bir parola uretir ve kendi ciktisinda BIR KEZ gosterir.
    Write-Host "  Demo giris bilgileri 'seed_demo' ciktisinda bir kez gosterildi." -ForegroundColor Yellow
    Write-Host "  Ornek verilerin tamami sentetiktir; gercek kullanimdan once temizleyin." -ForegroundColor Yellow
    Write-Host ""
}
Write-Host "  Belgeler:  README.md  ·  INSTALL_WINDOWS.md  ·  USER_GUIDE.md"
Write-Host ""
