@echo off
title Nodus
chcp 65001 > nul
cd /d "%~dp0"

echo ===================================================
echo                 NODUS BASLATILIYOR
echo ===================================================
echo.

:: Uygun Python (3.12 / 3.13) varsa onu kullan; yoksa Python 3.12'yi Nodus klasorune kendi kurar (yonetici izni gerekmez)
set "PYEXE="
if defined NODUS_FORCE_UV goto tryvenv
python -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] < (3,14) else 1)" >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if defined PYEXE goto havepython

:tryvenv
if not exist ".venv\Scripts\python.exe" goto dobootstrap
".venv\Scripts\python.exe" -c "import sys; sys.exit(0 if (3,12) <= sys.version_info[:2] < (3,14) else 1)" >nul 2>&1
if errorlevel 1 goto dobootstrap
set "PYEXE=%~dp0.venv\Scripts\python.exe"
goto havepython

:dobootstrap
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\bootstrap.ps1"
if errorlevel 1 goto bootfail
set "PYEXE=%~dp0.venv\Scripts\python.exe"
goto havepython

:bootfail
echo [HATA] Python 3.12 kurulamadi. Elle kurabilirsin: https://www.python.org/downloads/
if not defined NODUS_YES pause
exit /b 1

:havepython
:: Bagimlilik kontrolu: eksik kutuphaneler otomatik kurulur, kurulu olanlar atlanir
echo [1/2] Gerekli kutuphaneler denetleniyor...
"%PYEXE%" -m pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 echo [UYARI] Kutuphaneler denetlenemedi, internet yok olabilir. Kurulu olanlarla devam ediliyor...

:: Tam ekran uygulama penceresi acilir (Edge/Chrome yoksa varsayilan tarayici)
echo [2/2] Nodus penceresi aciliyor...
echo Kapatmak icin bu pencerede Ctrl + C tuslarina basabilirsin.
echo.

"%PYEXE%" server.py

if not defined NODUS_YES pause
