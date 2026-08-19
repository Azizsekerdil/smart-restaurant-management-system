<#
.SYNOPSIS
    Tek dosyalık Windows uygulaması (.exe) üretir.

.DESCRIPTION
    Sıra önemlidir:
      1. İkon üretilir (yoksa)
      2. Statik dosyalar ÜRETİM AYARLARIYLA toplanır
         DEBUG=False iken WhiteNoise hash'li dosya adları ve
         staticfiles.json manifestosu üretir. Bu manifesto pakete
         girmezse uygulama her sayfada 500 hatası verir.
      3. PyInstaller paketi oluşturur

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\build_exe.ps1
    .\scripts\build_exe.ps1 -SkipStatic     # statikleri yeniden toplama
#>

[CmdletBinding()]
param(
    [switch]$SkipStatic
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $ProjectRoot

$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[X] Sanal ortam bulunamadi. Once setup_windows.ps1 -Dev calistirin." -ForegroundColor Red
    exit 1
}

function Write-Step($m) { Write-Host ""; Write-Host "==> $m" -ForegroundColor Cyan }
function Write-Ok($m)   { Write-Host "    [OK] $m" -ForegroundColor Green }

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Blue
Write-Host "    AKILLI RESTAURANT - EXE PAKETLEME" -ForegroundColor Blue
Write-Host "  ============================================================" -ForegroundColor Blue

# ------------------------------------------------------------------ 1) PyInstaller
Write-Step "PyInstaller kontrol ediliyor"
& $venvPython -c "import PyInstaller" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "    PyInstaller kuruluyor..." -ForegroundColor Yellow
    & $venvPython -m pip install pyinstaller --quiet
}
$pyiVersion = & $venvPython -c "import PyInstaller; print(PyInstaller.__version__)"
Write-Ok "PyInstaller $pyiVersion"

# ------------------------------------------------------------------ 2) İkon
Write-Step "Uygulama ikonu"
if (Test-Path "assets\restaurant.ico") {
    Write-Ok "Mevcut ikon kullanilacak"
} else {
    & $venvPython scripts\make_icon.py | Out-Null
    Write-Ok "Ikon uretildi"
}

# ------------------------------------------------------------------ 3) Ceviriler
Write-Step "Ceviri katalogu derleniyor"
& $venvPython scripts\i18n_tools.py compile | Select-Object -Last 1
if (-not (Test-Path "locale\en\LC_MESSAGES\django.mo")) {
    Write-Host "    [X] django.mo uretilmedi; Ingilizce arayuz calismaz." -ForegroundColor Red
    exit 1
}
Write-Ok "Katalog hazir"

# ------------------------------------------------------------------ 4) Statik dosyalar
if (-not $SkipStatic) {
    Write-Step "Statik dosyalar toplaniyor (uretim ayarlariyla)"

    # KRITIK: DEBUG=False olmali. Aksi halde duz depolama kullanilir,
    # staticfiles.json uretilmez ve paketlenmis uygulama calisma aninda
    # "Missing staticfiles manifest entry" hatasi verir.
    $env:DJANGO_DEBUG = "False"
    $env:DJANGO_ENV = "production"
    $env:DJANGO_SECRET_KEY = "build-time-only-not-a-real-secret"

    # NOT: native komutlarda "2>&1" kullanmayin. Windows PowerShell 5.1
    # stderr satirlarini ErrorRecord'a sarar ve komut basarili donse bile
    # $ErrorActionPreference="Stop" ile script'i durdurur.
    & $venvPython manage.py collectstatic --noinput --clear | Select-Object -Last 1

    Remove-Item Env:\DJANGO_DEBUG, Env:\DJANGO_ENV, Env:\DJANGO_SECRET_KEY -ErrorAction SilentlyContinue

    if (-not (Test-Path "staticfiles\staticfiles.json")) {
        Write-Host "    [X] staticfiles.json uretilmedi." -ForegroundColor Red
        Write-Host "        Paketlenmis uygulama statik dosyalari sunamaz." -ForegroundColor Red
        exit 1
    }
    $entries = ((Get-Content "staticfiles\staticfiles.json" -Raw | ConvertFrom-Json).paths | Get-Member -MemberType NoteProperty).Count
    Write-Ok "Manifest uretildi ($entries dosya)"
}

# ------------------------------------------------------------------ 5) Paketleme
Write-Step "Paket olusturuluyor (birkac dakika surebilir)"

# PyInstaller ilerleme bilgisini stderr'e yazar; bu bir hata degildir.
# Ciktiyi dosyaya alip yalnizca sonucu gosteriyoruz.
$buildLog = Join-Path $ProjectRoot "build\pyinstaller.log"
New-Item -ItemType Directory -Force -Path (Split-Path $buildLog) | Out-Null

$prevPreference = $ErrorActionPreference
$ErrorActionPreference = "Continue"
& $venvPython -m PyInstaller restaurant.spec --noconfirm --log-level WARN *> $buildLog
$pyiExit = $LASTEXITCODE
$ErrorActionPreference = $prevPreference

if ($pyiExit -ne 0) {
    Write-Host "    [X] PyInstaller hata verdi (cikis kodu $pyiExit)." -ForegroundColor Red
    Get-Content $buildLog -Tail 25
    exit 1
}

$warnings = @(Get-Content $buildLog | Where-Object { $_ -match "^\d+ (WARNING|ERROR):" })
if ($warnings.Count -gt 0) {
    Write-Host "    $($warnings.Count) uyari (ayrinti: build\pyinstaller.log)" -ForegroundColor Yellow
}
Write-Ok "Derleme tamam"

$exe = Join-Path $ProjectRoot "dist\Akilli Restaurant.exe"
if (-not (Test-Path $exe)) {
    Write-Host "    [X] Paketleme basarisiz." -ForegroundColor Red
    exit 1
}

$sizeMb = [math]::Round((Get-Item $exe).Length / 1MB, 1)

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host "    PAKETLEME TAMAMLANDI" -ForegroundColor Green
Write-Host "  ============================================================" -ForegroundColor Green
Write-Host ""
Write-Host "    Dosya : $exe"
Write-Host "    Boyut : $sizeMb MB"
Write-Host ""
Write-Host "    Bu tek dosya calisir; Python kurulumu gerekmez." -ForegroundColor White
Write-Host "    Veritabani, medya ve gunlukler exe'nin YANINDA olusur," -ForegroundColor White
Write-Host "    bu yuzden exe'yi bos bir klasore koyun." -ForegroundColor White
Write-Host ""
