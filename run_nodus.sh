#!/usr/bin/env bash
# Nodus baslatici (macOS / Linux). Ilk calistirmada .venv olusturur ve kutuphaneleri kurar.
# Ortam degiskenleri: PYTHON (ornek: python3.12), NODUS_NO_VENV=1 (venv kullanma), NODUS_PORT, NODUS_NO_WINDOW=1
cd "$(dirname "$0")" || exit 1

echo "==================================================="
echo "                NODUS BASLATILIYOR"
echo "==================================================="

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
    for c in python3.12 python3; do   # Nodus Python 3.12 ile test edildi; varsa onu tercih et
        if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
    done
fi
if [ -z "$PY" ] || ! command -v "$PY" >/dev/null 2>&1; then
    echo "[HATA] Python bulunamadi. Kurulum: https://www.python.org/downloads/  (macOS: brew install python@3.12)"
    exit 1
fi
if ! "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)'; then
    echo "[HATA] Python 3.12 veya daha yenisi gerekli (bulunan: $("$PY" --version 2>&1))."
    echo "       macOS: brew install python@3.12   sonra:   PYTHON=python3.12 ./run_nodus.sh"
    exit 1
fi
if "$PY" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 14) else 1)'; then
    echo "[UYARI] Python 3.14+ ile bazi kutuphaneler (CoolProp vb.) hazir paket sunmayabilir. Sorun olursa Python 3.12 kullan."
fi

if [ -z "$NODUS_NO_VENV" ]; then
    # Homebrew/sistem Python'u pip ile dogrudan kurulumu reddeder (PEP 668): bu yuzden .venv
    if [ ! -d .venv ]; then
        echo "[0/2] Sanal ortam (.venv) olusturuluyor..."
        "$PY" -m venv .venv || { echo "[HATA] .venv olusturulamadi."; exit 1; }
    fi
    PY=".venv/bin/python"
fi

echo "[1/2] Gerekli kutuphaneler denetleniyor (ilk seferde birkac dakika surebilir)..."
if ! PIP_OUT=$("$PY" -m pip install -r requirements.txt --quiet --disable-pip-version-check 2>&1); then
    echo "[UYARI] Kutuphane kurulumunda hata (internet yok ya da Python surumu uyumsuz olabilir). Son satirlar:"
    echo "$PIP_OUT" | tail -8
    echo "        Kurulu olanlarla devam ediliyor..."
fi

echo "[2/2] Nodus penceresi aciliyor... Kapatmak icin Ctrl + C."
exec "$PY" server.py
