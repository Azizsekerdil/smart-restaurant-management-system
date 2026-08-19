@echo off
REM ============================================================
REM  Akilli Restaurant Yonetim Sistemi - gunluk kullanim
REM  Sunucuyu baslatir ve tarayiciyi acar.
REM  Masaustu kisayolu bu dosyayi calistirir.
REM ============================================================

setlocal EnableExtensions
cd /d "%~dp0"
title Akilli Restaurant Yonetim Sistemi - Sunucu

echo.
echo  ============================================================
echo    AKILLI RESTAURANT YONETIM SISTEMI
echo  ============================================================
echo.

REM ---------- Sanal ortam kontrolu ----------
if not exist ".venv\Scripts\python.exe" (
    echo  [X] Sanal ortam bulunamadi.
    echo.
    echo      Once kurulumu calistirin:
    echo          powershell -ExecutionPolicy Bypass -File setup_windows.ps1
    echo.
    pause
    exit /b 1
)

REM ---------- Sunucu zaten calisiyor mu? ----------
REM Ayni programi iki kez baslatmak "port kullanimda" hatasi verir.
REM Bu durumda yeni sunucu baslatmak yerine tarayiciyi acmak yeterlidir.
netstat -ano | findstr /R /C:"TCP.*:8000 .*LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo  [i] Sunucu zaten calisiyor.
    echo      Tarayici aciliyor: http://127.0.0.1:8000
    echo.
    start "" http://127.0.0.1:8000
    ping -n 3 127.0.0.1 >nul
    exit /b 0
)

REM ---------- Ortam dosyasi ----------
if not exist ".env" (
    echo  [!] .env dosyasi yok, ornekten olusturuluyor...
    copy ".env.example" ".env" >nul
)

REM ---------- Veritabani ----------
echo  [*] Veritabani kontrol ediliyor...
".venv\Scripts\python.exe" manage.py migrate --noinput
if errorlevel 1 (
    echo.
    echo  [X] Veritabani hazirlanamadi.
    echo      Ayrinti icin: logs\restaurant.log
    echo.
    pause
    exit /b 1
)

REM Not: Sistemde hic kullanici yoksa giris sayfasi bunu kendisi tespit
REM edip yonetici olusturma talimatini gosterir; burada ayrica kontrol
REM etmeye gerek yok.

REM ---------- Baslat ----------
echo  [*] Sunucu baslatiliyor...
echo.
echo      Adres  : http://127.0.0.1:8000
echo      Durdur : Bu pencerede Ctrl+C  (veya pencereyi kapatin)
echo.
echo  ------------------------------------------------------------

REM Sunucu ayaga kalkinca tarayiciyi ac
start "" /b cmd /c "ping -n 5 127.0.0.1 >nul && start """" http://127.0.0.1:8000"

".venv\Scripts\python.exe" manage.py runserver 127.0.0.1:8000

echo.
echo  ------------------------------------------------------------
echo  Sunucu durduruldu.
echo.
pause
endlocal
