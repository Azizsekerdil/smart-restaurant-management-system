<#
.SYNOPSIS
    Paketlenmiş uygulamayı kendi klasörüne kurar ve kısayolları oluşturur.

.DESCRIPTION
    Exe, veritabanını / günlükleri / medya dosyalarını KENDİ YANINDA
    oluşturur. Bu yüzden dist klasöründen değil, kalıcı bir klasörden
    çalıştırılmalıdır — aksi halde yeniden derleme sırasında veriler
    dist ile birlikte silinebilir.

    Bu script:
      1. D:\Restaurant\Uygulama klasörünü hazırlar
      2. dist\Akilli Restaurant.exe dosyasını oraya kopyalar
      3. Masaüstü (ve istenirse Başlat menüsü) kısayolunu oraya yöneltir

    Mevcut veritabanına dokunulmaz; yalnızca exe güncellenir.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\scripts\install_app.ps1
    .\scripts\install_app.ps1 -StartMenu
#>

[CmdletBinding()]
param(
    [switch]$StartMenu,
    [string]$Destination
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

$source = Join-Path $ProjectRoot "dist\Akilli Restaurant.exe"
if (-not $Destination) { $Destination = Join-Path $ProjectRoot "Uygulama" }
$target = Join-Path $Destination "Akilli Restaurant.exe"

Write-Host ""
Write-Host "  Akilli Restaurant - Kurulum" -ForegroundColor Cyan
Write-Host "  ---------------------------" -ForegroundColor Cyan

if (-not (Test-Path $source)) {
    Write-Host "  [X] Paket bulunamadi: $source" -ForegroundColor Red
    Write-Host "      Once derleyin: .\scripts\build_exe.ps1" -ForegroundColor Red
    exit 1
}

# Calisan bir kopya varsa dosya kilitli olur
$running = Get-Process -Name "Akilli Restaurant" -ErrorAction SilentlyContinue
if ($running) {
    Write-Host "  [!] Program calisiyor. Once kapatin:" -ForegroundColor Yellow
    $running | ForEach-Object { Write-Host "      PID $($_.Id)" -ForegroundColor Yellow }
    exit 1
}

New-Item -ItemType Directory -Force -Path $Destination | Out-Null

$isUpdate = Test-Path $target
Copy-Item $source -Destination $target -Force
Write-Host "  [OK] $(if ($isUpdate) { 'Guncellendi' } else { 'Kuruldu' }): $target" -ForegroundColor Green

$db = Join-Path $Destination "restaurant.sqlite3"
if (Test-Path $db) {
    $mb = [math]::Round((Get-Item $db).Length / 1MB, 1)
    Write-Host "  [OK] Mevcut veritabani korundu ($mb MB)" -ForegroundColor Green
} else {
    Write-Host "  [*] Ilk calistirmada kurulum sihirbazi acilacak" -ForegroundColor White
}

# Kisayollar
# NOT: splatting icin hashtable kullanilmali; dizi splatting'i argumanlari
# konumsal gecer ve "-Target" bir parametre adi degil, deger olarak gider.
$shortcutArgs = @{ Target = $target }
if ($StartMenu) { $shortcutArgs["StartMenu"] = $true }
& (Join-Path $ProjectRoot "scripts\create_shortcut.ps1") @shortcutArgs
