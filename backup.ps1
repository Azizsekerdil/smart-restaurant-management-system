<#
.SYNOPSIS
    Veritabanı, medya dosyaları ve yapılandırmayı tek bir ZIP dosyasına yedekler.

.DESCRIPTION
    Yedek içeriği: veritabanı (SQLite dosyası veya PostgreSQL dökümü),
    media/ klasörü, .env, requirements dosyaları ve bir bilgi dosyası.

    UYARI: Yedek .env dosyasını içerir; bu dosyada API anahtarlarınız bulunur.
    Yedeği güvenli bir yerde saklayın, e-posta veya bulut ile paylaşmayın.

.EXAMPLE
    .\backup.ps1
    .\backup.ps1 -Destination E:\Yedekler
    .\backup.ps1 -KeepLast 14         # son 14 yedeği tut, eskileri sil
    .\backup.ps1 -NoEnv               # .env dosyasını yedeğe dahil etme
#>

[CmdletBinding()]
param(
    [string]$Destination = "",
    [int]$KeepLast = 30,
    [switch]$NoEnv
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

if (-not $Destination) { $Destination = Join-Path $ProjectRoot "backups" }
if (-not (Test-Path $Destination)) { New-Item -ItemType Directory -Path $Destination | Out-Null }

$stamp      = Get-Date -Format "yyyyMMdd-HHmmss"
$stageDir   = Join-Path $env:TEMP "restaurant-backup-$stamp"
$archive    = Join-Path $Destination "yedek-$stamp.zip"
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

New-Item -ItemType Directory -Path $stageDir | Out-Null

Write-Host ""
Write-Host "  AKILLI RESTAURANT - Yedekleme" -ForegroundColor Cyan
Write-Host "  ------------------------------" -ForegroundColor Cyan

try {
    # -------------------------------------------------------- veritabanı
    Write-Host "  [*] Veritabani yedekleniyor..."
    $dbEngine = "sqlite"
    if (Test-Path ".env") {
        $line = Select-String -Path ".env" -Pattern "^DB_ENGINE=(.+)$" | Select-Object -First 1
        if ($line) { $dbEngine = $line.Matches[0].Groups[1].Value.Trim() }
    }

    if ($dbEngine -match "postgres") {
        # PostgreSQL: mantıksal döküm
        $env:PGPASSWORD = (Select-String -Path ".env" -Pattern "^DB_PASSWORD=(.*)$").Matches[0].Groups[1].Value
        $dbName = (Select-String -Path ".env" -Pattern "^DB_NAME=(.+)$").Matches[0].Groups[1].Value.Trim()
        $dbUser = (Select-String -Path ".env" -Pattern "^DB_USER=(.+)$").Matches[0].Groups[1].Value.Trim()
        $dbHost = (Select-String -Path ".env" -Pattern "^DB_HOST=(.+)$").Matches[0].Groups[1].Value.Trim()
        pg_dump -h $dbHost -U $dbUser -d $dbName -F c -f (Join-Path $stageDir "database.dump")
        Remove-Item Env:\PGPASSWORD
        Write-Host "      PostgreSQL dokumu alindi" -ForegroundColor Green
    } else {
        # SQLite: WAL dahil tutarlı kopya için Django'nun bağlantısını kullan
        $sqliteFiles = Get-ChildItem -Path $ProjectRoot -Filter "*.sqlite3" -File
        if ($sqliteFiles.Count -eq 0) {
            Write-Host "      [!] Veritabani dosyasi bulunamadi" -ForegroundColor Yellow
        }
        foreach ($file in $sqliteFiles) {
            Copy-Item $file.FullName (Join-Path $stageDir $file.Name)
            # WAL ve SHM dosyaları da varsa kopyala (tutarlılık için)
            foreach ($suffix in @("-wal", "-shm")) {
                $extra = "$($file.FullName)$suffix"
                if (Test-Path $extra) { Copy-Item $extra (Join-Path $stageDir "$($file.Name)$suffix") }
            }
            Write-Host "      $($file.Name) kopyalandi" -ForegroundColor Green
        }
    }

    # -------------------------------------------------------- JSON döküm (taşınabilir)
    if (Test-Path $venvPython) {
        Write-Host "  [*] Tasinabilir JSON dokumu aliniyor..."
        & $venvPython manage.py dumpdata --natural-foreign --natural-primary `
            -e contenttypes -e auth.Permission -e sessions -e admin.logentry -e axes `
            --indent 2 -o (Join-Path $stageDir "veri.json") 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "      veri.json olusturuldu" -ForegroundColor Green
        } else {
            Write-Host "      [!] JSON dokumu alinamadi (kritik degil)" -ForegroundColor Yellow
        }
    }

    # -------------------------------------------------------- medya
    if ((Test-Path "media") -and (Get-ChildItem "media" -Recurse -File | Measure-Object).Count -gt 0) {
        Write-Host "  [*] Medya dosyalari yedekleniyor..."
        Copy-Item "media" (Join-Path $stageDir "media") -Recurse
        Write-Host "      media/ kopyalandi" -ForegroundColor Green
    }

    # -------------------------------------------------------- yapılandırma
    Write-Host "  [*] Yapilandirma yedekleniyor..."
    foreach ($file in @("requirements.txt", "requirements-dev.txt", "requirements-optional.txt", ".env.example")) {
        if (Test-Path $file) { Copy-Item $file $stageDir }
    }
    if ((Test-Path ".env") -and (-not $NoEnv)) {
        Copy-Item ".env" $stageDir
        Write-Host "      .env dahil edildi (API anahtarlari icerir!)" -ForegroundColor Yellow
    }

    # -------------------------------------------------------- bilgi dosyası
    @"
Akilli Restaurant Yonetim Sistemi - Yedek
==========================================
Olusturulma : $(Get-Date -Format 'dd.MM.yyyy HH:mm:ss')
Bilgisayar  : $env:COMPUTERNAME
Kullanici   : $env:USERNAME
Proje       : $ProjectRoot
Veritabani  : $dbEngine
.env dahil  : $(if ($NoEnv) { 'HAYIR' } else { 'EVET - gizli anahtar icerir' })

Geri yukleme:
    .\restore.ps1 -BackupFile "$archive"

UYARI: Bu arsiv musteri kisisel verileri ve (dahil edilmisse) API
anahtarlari icerir. Guvenli bir yerde saklayin.
"@ | Set-Content (Join-Path $stageDir "YEDEK_BILGISI.txt") -Encoding UTF8

    # -------------------------------------------------------- arşivle
    Write-Host "  [*] Arsivleniyor..."
    Compress-Archive -Path (Join-Path $stageDir "*") -DestinationPath $archive -CompressionLevel Optimal
    $sizeMb = [math]::Round((Get-Item $archive).Length / 1MB, 2)

    Write-Host ""
    Write-Host "  [OK] Yedek olusturuldu" -ForegroundColor Green
    Write-Host "       $archive  ($sizeMb MB)"

    # -------------------------------------------------------- eski yedekleri temizle
    if ($KeepLast -gt 0) {
        $old = Get-ChildItem $Destination -Filter "yedek-*.zip" |
               Sort-Object LastWriteTime -Descending | Select-Object -Skip $KeepLast
        if ($old) {
            $old | Remove-Item -Force
            Write-Host "       $($old.Count) eski yedek silindi (son $KeepLast tutuluyor)" -ForegroundColor DarkGray
        }
    }
    Write-Host ""
}
finally {
    if (Test-Path $stageDir) { Remove-Item $stageDir -Recurse -Force -ErrorAction SilentlyContinue }
}
