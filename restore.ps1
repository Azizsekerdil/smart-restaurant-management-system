<#
.SYNOPSIS
    backup.ps1 ile alınmış bir yedeği geri yükler.

.DESCRIPTION
    Geri yüklemeden ÖNCE mevcut durumun güvenlik yedeğini alır ve onay ister.

.EXAMPLE
    .\restore.ps1                                        # en son yedeği listeler
    .\restore.ps1 -BackupFile backups\yedek-20260815-030000.zip
    .\restore.ps1 -BackupFile ... -Force                 # onay sorma
    .\restore.ps1 -BackupFile ... -SkipEnv               # .env dosyasını geri yükleme
#>

[CmdletBinding()]
param(
    [string]$BackupFile = "",
    [switch]$Force,
    [switch]$SkipEnv
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ProjectRoot

Write-Host ""
Write-Host "  AKILLI RESTAURANT - Geri Yukleme" -ForegroundColor Cyan
Write-Host "  ---------------------------------" -ForegroundColor Cyan

# ------------------------------------------------------------------ yedek seç
if (-not $BackupFile) {
    $backupDir = Join-Path $ProjectRoot "backups"
    if (-not (Test-Path $backupDir)) {
        Write-Host "  [X] backups klasoru bulunamadi." -ForegroundColor Red
        exit 1
    }
    $available = Get-ChildItem $backupDir -Filter "yedek-*.zip" | Sort-Object LastWriteTime -Descending
    if (-not $available) {
        Write-Host "  [X] Hicbir yedek bulunamadi." -ForegroundColor Red
        exit 1
    }

    Write-Host "  Mevcut yedekler:"
    Write-Host ""
    for ($i = 0; $i -lt [Math]::Min($available.Count, 15); $i++) {
        $f = $available[$i]
        Write-Host ("    [{0,2}] {1}  ({2:N1} MB)  {3:dd.MM.yyyy HH:mm}" -f `
            ($i + 1), $f.Name, ($f.Length / 1MB), $f.LastWriteTime)
    }
    Write-Host ""
    $choice = Read-Host "  Numara secin (iptal icin Enter)"
    if (-not $choice) { Write-Host "  Iptal edildi."; exit 0 }
    $BackupFile = $available[[int]$choice - 1].FullName
}

if (-not (Test-Path $BackupFile)) {
    Write-Host "  [X] Dosya bulunamadi: $BackupFile" -ForegroundColor Red
    exit 1
}

$BackupFile = (Resolve-Path $BackupFile).Path
Write-Host ""
Write-Host "  Secilen yedek: $BackupFile"

# ------------------------------------------------------------------ içeriği göster
$stageDir = Join-Path $env:TEMP "restaurant-restore-$(Get-Date -Format 'yyyyMMddHHmmss')"
New-Item -ItemType Directory -Path $stageDir | Out-Null

try {
    Expand-Archive -Path $BackupFile -DestinationPath $stageDir -Force

    $infoFile = Join-Path $stageDir "YEDEK_BILGISI.txt"
    if (Test-Path $infoFile) {
        Write-Host ""
        Get-Content $infoFile | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkGray }
    }

    # -------------------------------------------------------- onay
    if (-not $Force) {
        Write-Host ""
        Write-Host "  DIKKAT: Mevcut veritabani ve medya dosyalari DEGISTIRILECEK." -ForegroundColor Yellow
        Write-Host "          Islem oncesi otomatik guvenlik yedegi alinacak." -ForegroundColor Yellow
        Write-Host ""
        $answer = Read-Host "  Devam edilsin mi? Onaylamak icin 'EVET' yazin"
        if ($answer -ne "EVET") { Write-Host "  Iptal edildi."; exit 0 }
    }

    # -------------------------------------------------------- güvenlik yedeği
    Write-Host ""
    Write-Host "  [*] Mevcut durumun guvenlik yedegi aliniyor..."
    & (Join-Path $ProjectRoot "backup.ps1") -KeepLast 0 | Out-Null
    Write-Host "      Tamamlandi" -ForegroundColor Green

    # -------------------------------------------------------- veritabanı
    Write-Host "  [*] Veritabani geri yukleniyor..."
    $sqliteBackups = Get-ChildItem $stageDir -Filter "*.sqlite3" -File
    $pgDump = Join-Path $stageDir "database.dump"

    if ($sqliteBackups) {
        foreach ($file in $sqliteBackups) {
            $target = Join-Path $ProjectRoot $file.Name
            # Eski WAL/SHM dosyalarını temizle, aksi hâlde tutarsızlık olur
            foreach ($suffix in @("-wal", "-shm")) {
                $stale = "$target$suffix"
                if (Test-Path $stale) { Remove-Item $stale -Force }
            }
            Copy-Item $file.FullName $target -Force
            foreach ($suffix in @("-wal", "-shm")) {
                $extra = Join-Path $stageDir "$($file.Name)$suffix"
                if (Test-Path $extra) { Copy-Item $extra "$target$suffix" -Force }
            }
            Write-Host "      $($file.Name)" -ForegroundColor Green
        }
    } elseif (Test-Path $pgDump) {
        Write-Host "      PostgreSQL dokumu bulundu." -ForegroundColor Yellow
        Write-Host "      Elle geri yukleyin:" -ForegroundColor Yellow
        Write-Host "        pg_restore -h <host> -U <kullanici> -d <veritabani> -c `"$pgDump`""
    } else {
        Write-Host "      [!] Yedekte veritabani bulunamadi" -ForegroundColor Yellow
    }

    # -------------------------------------------------------- medya
    $mediaBackup = Join-Path $stageDir "media"
    if (Test-Path $mediaBackup) {
        Write-Host "  [*] Medya dosyalari geri yukleniyor..."
        $mediaTarget = Join-Path $ProjectRoot "media"
        if (Test-Path $mediaTarget) { Remove-Item $mediaTarget -Recurse -Force }
        Copy-Item $mediaBackup $mediaTarget -Recurse
        Write-Host "      media/" -ForegroundColor Green
    }

    # -------------------------------------------------------- .env
    $envBackup = Join-Path $stageDir ".env"
    if ((Test-Path $envBackup) -and (-not $SkipEnv)) {
        Write-Host "  [*] .env geri yukleniyor..."
        Copy-Item $envBackup (Join-Path $ProjectRoot ".env") -Force
        Write-Host "      .env" -ForegroundColor Green
    }

    # -------------------------------------------------------- migrate
    $venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
    if (Test-Path $venvPython) {
        Write-Host "  [*] Veritabani semasi guncelleniyor..."
        & $venvPython manage.py migrate --noinput
    }

    Write-Host ""
    Write-Host "  [OK] Geri yukleme tamamlandi." -ForegroundColor Green
    Write-Host "       Uygulamayi baslatin:  .\run_app.bat"
    Write-Host ""
}
finally {
    if (Test-Path $stageDir) { Remove-Item $stageDir -Recurse -Force -ErrorAction SilentlyContinue }
}
