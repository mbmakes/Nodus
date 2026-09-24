@echo off
title Nodus Platform Launcher
chcp 65001 > nul
cd /d "%~dp0"

echo ===================================================
echo               NODUS ENGINE BASLATILIYOR           
echo ===================================================
echo.

:: Bagimlilik kontrolu ve eksik kutuphanelerin kurulumu
echo [1/2] Gerekli kutuphaneler denetleniyor...
python -m pip install -r requirements.txt --quiet --disable-pip-version-check
if %errorlevel% neq 0 (
    echo [HATA] Kutuphaneler yuklenirken bir sorun olustu.
    pause
    exit /b
)

:: Arayuzu ayaga kaldir
echo [2/2] Nodus arayuzu baslatiliyor...
echo Tarayici otomatik olarak acilacak (http://localhost:8501)
echo Kapatmak icin bu pencerede Ctrl + C tuslarina basabilirsin.
echo.

python -m streamlit run app.py

pause