@echo off
title Nodus
chcp 65001 > nul
cd /d "%~dp0"

echo ===================================================
echo                 NODUS BASLATILIYOR
echo ===================================================
echo.

:: Bagimlilik kontrolu: eksik kutuphaneler otomatik kurulur, kurulu olanlar atlanir
echo [1/2] Gerekli kutuphaneler denetleniyor...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo [UYARI] Kutuphaneler denetlenemedi, internet yok olabilir. Kurulu olanlarla devam ediliyor...
)

:: Tam ekran uygulama penceresi acilir (Edge/Chrome yoksa varsayilan tarayici)
echo [2/2] Nodus penceresi aciliyor...
echo Kapatmak icin bu pencerede Ctrl + C tuslarina basabilirsin.
echo.

python server.py

pause
