<#
.SYNOPSIS
    Masaüstüne "Akıllı Restaurant" kısayolu oluşturur.

.DESCRIPTION
    Hedef otomatik seçilir:
      1. Uygulama\Akilli Restaurant.exe   (paketlenmiş sürüm — önerilen)
      2. run_app.bat                      (kaynaktan çalıştırma)

    -Target ile hedef doğrudan verilebilir (bkz. install_app.ps1).

    İkon programatik olarak üretilmiş assets/restaurant.ico dosyasıdır.
    OneDrive ile yönlendirilmiş masaüstü klasörleri de doğru bulunur.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\create_shortcut.ps1
    .\scripts\create_shortcut.ps1 -StartMenu     # Başlat menüsüne de ekle
    .\scripts\create_shortcut.ps1 -Source        # kaynaktan çalıştırmayı seç
    .\scripts\create_shortcut.ps1 -Remove        # kısayolu kaldır
#>

[CmdletBinding()]
param(
    [switch]$StartMenu,
    [switch]$Remove,
    [switch]$Source,
    [string]$Target
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$ShortcutName = "Akıllı Restaurant.lnk"
$IconPath     = Join-Path $ProjectRoot "assets\restaurant.ico"

# ------------------------------------------------------------------ hedef
$packaged = Join-Path $ProjectRoot "Uygulama\Akilli Restaurant.exe"
$batch    = Join-Path $ProjectRoot "run_app.bat"

if (-not $Target) {
    if ($Source)                  { $Target = $batch }
    elseif (Test-Path $packaged)  { $Target = $packaged }
    else                          { $Target = $batch }
}

# Exe verisini kendi klasorune yazar; bat ise proje kokunden calisir.
$WorkingDir = Split-Path -Parent $Target

# Masaüstü yolu (OneDrive yönlendirmesi dahil doğru sonuç verir)
$Desktop = [Environment]::GetFolderPath("Desktop")
$DesktopLink = Join-Path $Desktop $ShortcutName

$StartMenuDir = Join-Path ([Environment]::GetFolderPath("Programs")) "Akıllı Restaurant"
$StartMenuLink = Join-Path $StartMenuDir $ShortcutName

function New-Shortcut {
    param([string]$Path)

    $dir = Split-Path -Parent $Path
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }

    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($Path)
    $link.TargetPath       = $Target
    $link.WorkingDirectory = $WorkingDir
    $link.Description      = "Akıllı Restaurant Yönetim Sistemi - POS, mutfak ekranı, stok ve raporlama"
    $link.WindowStyle      = 1        # normal pencere (Ctrl+C ile durdurulabilsin)
    if (Test-Path $IconPath) { $link.IconLocation = "$IconPath,0" }
    $link.Save()

    [Runtime.InteropServices.Marshal]::ReleaseComObject($shell) | Out-Null
}

Write-Host ""
Write-Host "  Akilli Restaurant - Kisayol" -ForegroundColor Cyan
Write-Host "  ---------------------------" -ForegroundColor Cyan

# ------------------------------------------------------------------ kaldır
if ($Remove) {
    foreach ($path in @($DesktopLink, $StartMenuLink)) {
        if (Test-Path $path) { Remove-Item $path -Force; Write-Host "  [OK] Silindi: $path" -ForegroundColor Green }
    }
    if ((Test-Path $StartMenuDir) -and -not (Get-ChildItem $StartMenuDir)) { Remove-Item $StartMenuDir -Force }
    Write-Host ""
    exit 0
}

# ------------------------------------------------------------------ ön kontrol
if (-not (Test-Path $Target)) {
    Write-Host "  [X] Hedef bulunamadi: $Target" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $IconPath)) {
    Write-Host "  [*] Ikon bulunamadi, uretiliyor..." -ForegroundColor Yellow
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        & $venvPython (Join-Path $ProjectRoot "scripts\make_icon.py") | Out-Null
    }
    if (-not (Test-Path $IconPath)) {
        Write-Host "  [!] Ikon uretilemedi; kisayol varsayilan ikonla olusturulacak." -ForegroundColor Yellow
    }
}

# ------------------------------------------------------------------ oluştur
$isExe = $Target.EndsWith(".exe")

New-Shortcut -Path $DesktopLink
Write-Host "  [OK] Masaustu kisayolu olusturuldu" -ForegroundColor Green
Write-Host "       $DesktopLink"
Write-Host "       -> $Target" -ForegroundColor DarkGray

if ($StartMenu) {
    New-Shortcut -Path $StartMenuLink
    Write-Host "  [OK] Baslat menusune eklendi" -ForegroundColor Green
    Write-Host "       $StartMenuLink"
}

Write-Host ""
Write-Host "  Kisayola cift tiklayin:" -ForegroundColor White
if ($isExe) {
    Write-Host "    - Python kurulumu gerekmez (her sey exe icinde)"
    Write-Host "    - Ilk calistirmada kurulum sihirbazi acilir"
} else {
    Write-Host "    - Sanal ortam ve veritabani kontrol edilir"
}
Write-Host "    - Sunucu baslar, tarayici otomatik acilir"
Write-Host ""
Write-Host "  Durdurmak icin acilan siyah pencerede Ctrl+C." -ForegroundColor DarkGray
Write-Host ""
