<#
.SYNOPSIS
    Geliştirici sunucusu — otomatik yeniden yükleme ve ayrıntılı günlük.

.EXAMPLE
    .\run_dev.ps1
    .\run_dev.ps1 -Port 8080
    .\run_dev.ps1 -Network          # ağdaki diğer cihazlardan erişilebilir
    .\run_dev.ps1 -Migrate -Static  # başlamadan önce migrate + collectstatic
#>

[CmdletBinding()]
param(
    [int]$Port = 8000,
    [switch]$Network,   # 0.0.0.0 üzerinde dinle
    [switch]$Migrate,   # önce veritabanını güncelle
    [switch]$Static     # önce statik dosyaları topla
)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)

$venvPython = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "[X] Sanal ortam bulunamadi. Once setup_windows.ps1 calistirin." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "  AKILLI RESTAURANT - Gelistirici Sunucusu" -ForegroundColor Cyan
Write-Host "  ----------------------------------------" -ForegroundColor Cyan

if ($Migrate) {
    Write-Host "  [*] Veritabani guncelleniyor..." -ForegroundColor Yellow
    & $venvPython manage.py migrate --noinput
}
if ($Static) {
    Write-Host "  [*] Statik dosyalar toplaniyor..." -ForegroundColor Yellow
    & $venvPython manage.py collectstatic --noinput | Out-Null
}

# Yapilandirma kontrolu
& $venvPython manage.py check 2>&1 | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "  [X] Yapilandirma hatasi:" -ForegroundColor Red
    & $venvPython manage.py check
    exit 1
}
Write-Host "  [OK] Yapilandirma dogrulandi" -ForegroundColor Green

# LM Studio durumu (bilgi amacli)
try {
    $models = Invoke-RestMethod -Uri "http://127.0.0.1:1234/v1/models" -TimeoutSec 3
    Write-Host "  [OK] LM Studio calisiyor ($($models.data.Count) model)" -ForegroundColor Green
} catch {
    Write-Host "  [!]  LM Studio kapali - yapay zeka ozellikleri devre disi" -ForegroundColor DarkYellow
}

$bindAddress = if ($Network) { "0.0.0.0" } else { "127.0.0.1" }

Write-Host ""
Write-Host "  Adres:  http://127.0.0.1:$Port" -ForegroundColor White
if ($Network) {
    $localIp = (Get-NetIPAddress -AddressFamily IPv4 |
                Where-Object { $_.IPAddress -notlike "127.*" -and $_.PrefixOrigin -ne "WellKnown" } |
                Select-Object -First 1).IPAddress
    if ($localIp) {
        Write-Host "  Ag:     http://${localIp}:$Port" -ForegroundColor White
        Write-Host ""
        Write-Host "  [!] Ag erisimi icin .env dosyasinda su satirlari guncelleyin:" -ForegroundColor Yellow
        Write-Host "      DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,$localIp"
        Write-Host "      DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:$Port,http://${localIp}:$Port"
    }
}
Write-Host ""
Write-Host "  Durdurmak icin Ctrl+C" -ForegroundColor DarkGray
Write-Host ""

& $venvPython manage.py runserver "${bindAddress}:$Port"
