#!/usr/bin/env bash
# Nodus baslatici (macOS / Linux). Ilk calistirmada .venv olusturur ve kutuphaneleri kurar.
# Ortam degiskenleri: PYTHON (varsayilan python3), NODUS_NO_VENV=1 (venv kullanma), NODUS_PORT, NODUS_NO_WINDOW=1
cd "$(dirname "$0")" || exit 1

echo "==================================================="
echo "                NODUS BASLATILIYOR"
echo "==================================================="

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
    echo "[HATA] Python bulunamadi. Kurulum: https://www.python.org/downloads/  (macOS: brew install python@3.12)"
    exit 1
fi

if [ -z "$NODUS_NO_VENV" ]; then
    # Homebrew/sistem Python'u pip ile dogrudan kurulumu reddeder (PEP 668): bu yuzden .venv
    if [ ! -d .venv ]; then
        echo "[0/2] Sanal ortam (.venv) olusturuluyor..."
        "$PY" -m venv .venv || { echo "[HATA] .venv olusturulamadi."; exit 1; }
    fi
    PY=".venv/bin/python"
fi

echo "[1/2] Gerekli kutuphaneler denetleniyor..."
"$PY" -m pip install -r requirements.txt --quiet --disable-pip-version-check \
    || echo "[UYARI] Kutuphaneler denetlenemedi, internet yok olabilir. Kurulu olanlarla devam ediliyor..."

echo "[2/2] Nodus penceresi aciliyor... Kapatmak icin Ctrl + C."
exec "$PY" server.py
