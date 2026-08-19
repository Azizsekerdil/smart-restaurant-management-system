<#
.SYNOPSIS
    Tüm testleri ve kalite kontrollerini çalıştırır, TEST_REPORT.md üretir.

.EXAMPLE
    .\test_all.ps1
    .\test_all.ps1 -Fix         # düzeltilebilir lint/format sorunlarını onar
    .\test_all.ps1 -Quick       # yalnızca testler (lint/güvenlik atlanır)
    .\test_all.ps1 -NoReport    # rapor dosyası yazma
#>

[CmdletBinding()]
param(
    [switch]$Fix,
    [switch]$Quick,
    [switch]$NoReport
)

Set-Location (Split-Path -Parent $MyInvocation.MyCommand.Path)
$venvPython = ".\.venv\Scripts\python.exe"

if (-not (Test-Path $venvPython)) {
    Write-Host "[X] Sanal ortam bulunamadi. Once setup_windows.ps1 -Dev calistirin." -ForegroundColor Red
    exit 1
}

$results = [ordered]@{}
$startTime = Get-Date

function Invoke-Check {
    param([string]$Name, [scriptblock]$Command, [switch]$Optional)

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan
    $output = & $Command 2>&1 | Out-String
    $ok = ($LASTEXITCODE -eq 0)

    $trimmed = ($output -split "`n" | Where-Object { $_.Trim() -ne "" } | Select-Object -Last 12) -join "`n"
    Write-Host $trimmed

    if ($ok) {
        Write-Host "    [GECTI] $Name" -ForegroundColor Green
    } elseif ($Optional) {
        Write-Host "    [UYARI] $Name (zorunlu degil)" -ForegroundColor Yellow
    } else {
        Write-Host "    [KALDI] $Name" -ForegroundColor Red
    }

    $script:results[$Name] = @{
        Passed   = $ok
        Optional = [bool]$Optional
        Output   = $trimmed
    }
    return $ok
}

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Blue
Write-Host "    KALITE VE TEST KONTROLLERI" -ForegroundColor Blue
Write-Host "  ============================================================" -ForegroundColor Blue

# ------------------------------------------------------------------ düzeltme
if ($Fix) {
    Write-Host ""
    Write-Host "==> Otomatik duzeltmeler uygulaniyor" -ForegroundColor Yellow
    & $venvPython -m ruff check . --fix
    & $venvPython -m black .
}

# ------------------------------------------------------------------ kontroller
Invoke-Check "Django yapilandirma" { & $venvPython manage.py check } | Out-Null
Invoke-Check "Eksik migration kontrolu" {
    & $venvPython manage.py makemigrations --check --dry-run
} | Out-Null

if (-not $Quick) {
    Invoke-Check "Ruff (linter)"        { & $venvPython -m ruff check . } | Out-Null
    Invoke-Check "Black (bicimlendirme)" { & $venvPython -m black --check . } | Out-Null
    Invoke-Check "Mypy (tip denetimi)"  { & $venvPython -m mypy apps } -Optional | Out-Null
}

Invoke-Check "Pytest (birim + entegrasyon)" {
    & $venvPython -m pytest -q --cov=apps --cov-report=term-missing:skip-covered
} | Out-Null

if (-not $Quick) {
    Invoke-Check "Bandit (guvenlik taramasi)" {
        & $venvPython -m bandit -c pyproject.toml -r apps config -q
    } | Out-Null
    Invoke-Check "pip-audit (bagimlilik aciklari)" {
        & $venvPython -m pip_audit --progress-spinner off
    } | Out-Null
}

# ------------------------------------------------------------------ özet
$duration = [math]::Round(((Get-Date) - $startTime).TotalSeconds, 1)
$required = $results.GetEnumerator() | Where-Object { -not $_.Value.Optional }
$failed   = $required | Where-Object { -not $_.Value.Passed }

Write-Host ""
Write-Host "  ============================================================" -ForegroundColor Blue
Write-Host "    OZET  ($duration saniye)" -ForegroundColor Blue
Write-Host "  ============================================================" -ForegroundColor Blue
foreach ($entry in $results.GetEnumerator()) {
    $status = if ($entry.Value.Passed) { "GECTI " } elseif ($entry.Value.Optional) { "UYARI " } else { "KALDI " }
    $color  = if ($entry.Value.Passed) { "Green" } elseif ($entry.Value.Optional) { "Yellow" } else { "Red" }
    Write-Host ("    [{0}] {1}" -f $status, $entry.Key) -ForegroundColor $color
}
Write-Host ""

# ------------------------------------------------------------------ rapor
if (-not $NoReport) {
    $lines = @()
    $lines += "# Test Raporu"
    $lines += ""
    $lines += "Bu dosya ``test_all.ps1`` tarafindan otomatik uretilmistir."
    $lines += ""
    $lines += "| Alan | Deger |"
    $lines += "|---|---|"
    $lines += "| Calistirma zamani | $(Get-Date -Format 'dd.MM.yyyy HH:mm') |"
    $lines += "| Sure | $duration saniye |"
    $lines += "| Python | $(& $venvPython --version) |"
    $lines += "| Isletim sistemi | $([System.Environment]::OSVersion.VersionString) |"
    $lines += ""
    $lines += "## Sonuclar"
    $lines += ""
    $lines += "| Kontrol | Sonuc |"
    $lines += "|---|---|"
    foreach ($entry in $results.GetEnumerator()) {
        $mark = if ($entry.Value.Passed) { "PASS" } elseif ($entry.Value.Optional) { "WARN (zorunlu degil)" } else { "FAIL" }
        $lines += "| $($entry.Key) | $mark |"
    }
    $lines += ""
    $lines += "## Ayrintilar"
    foreach ($entry in $results.GetEnumerator()) {
        $lines += ""
        $lines += "### $($entry.Key)"
        $lines += ""
        $lines += '```'
        $lines += $entry.Value.Output
        $lines += '```'
    }
    $lines | Set-Content "TEST_REPORT.md" -Encoding UTF8
    Write-Host "  Rapor yazildi: TEST_REPORT.md" -ForegroundColor DarkGray
    Write-Host ""
}

if ($failed.Count -gt 0) {
    Write-Host "  $($failed.Count) zorunlu kontrol basarisiz." -ForegroundColor Red
    exit 1
}
Write-Host "  Tum zorunlu kontroller gecti." -ForegroundColor Green
exit 0
