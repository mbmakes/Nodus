#!/usr/bin/env bash
# Nodus baslatici (macOS / Linux). Python 3.12 yoksa kendi kurar (yonetici sifresi gerekmez), .venv olusturur,
# kutuphaneleri kurar ve Nodus'u acar.
# Ortam: PYTHON (belirli yorumlayici), NODUS_NO_VENV=1, NODUS_FORCE_UV=1 (test: Python'u uv ile kur), NODUS_YES=1 (soru sorma),
#        NODUS_PORT, NODUS_NO_WINDOW=1
cd "$(dirname "$0")" || exit 1

echo "==================================================="
echo "                NODUS BASLATILIYOR"
echo "==================================================="

py_ok() {   # Nodus 3.12 ile test edildi; 3.12 ve 3.13 kabul, 3.14+ icin hazir paket olmayabilir
    "$1" -c 'import sys; sys.exit(0 if (3, 12) <= sys.version_info[:2] < (3, 14) else 1)' 2>/dev/null
}

bootstrap_uv() {
    echo "Python 3.12 bulunamadi (ya da surumu uygun degil)."
    echo "Nodus klasorune (.nodus_tools/ ve .venv/) tasinabilir bir Python 3.12 kurulacak (~60 MB)."
    echo "Yonetici sifresi gerekmez, sistemine dokunulmaz; klasoru silince hepsi gider."
    if [ -z "$NODUS_YES" ] && [ -t 0 ]; then
        read -r -p "Devam edilsin mi? [E/h] " ans
        case "$ans" in [hHnN]*) echo "Iptal edildi."; exit 1 ;; esac
    fi
    case "$(uname -s)-$(uname -m)" in
        Darwin-arm64) T=aarch64-apple-darwin ;;
        Darwin-x86_64) T=x86_64-apple-darwin ;;
        Linux-x86_64) T=x86_64-unknown-linux-gnu ;;
        Linux-aarch64) T=aarch64-unknown-linux-gnu ;;
        *) echo "[HATA] Bu platform icin otomatik kurulum yok ($(uname -s)-$(uname -m)). Python 3.12'yi elle kur."; exit 1 ;;
    esac
    mkdir -p .nodus_tools
    URL="https://github.com/astral-sh/uv/releases/latest/download/uv-$T.tar.gz"
    echo "[0/2] Python kurulum araci (uv) indiriliyor..."
    curl -fsSL "$URL" -o .nodus_tools/uv.tar.gz && curl -fsSL "$URL.sha256" -o .nodus_tools/uv.tar.gz.sha256 \
        || { echo "[HATA] uv indirilemedi (internet?)."; exit 1; }
    WANT=$(awk '{print $1}' .nodus_tools/uv.tar.gz.sha256)
    if command -v shasum >/dev/null 2>&1; then GOT=$(shasum -a 256 .nodus_tools/uv.tar.gz | awk '{print $1}'); else GOT=$(sha256sum .nodus_tools/uv.tar.gz | awk '{print $1}'); fi
    if [ -z "$WANT" ] || [ "$WANT" != "$GOT" ]; then
        echo "[HATA] Indirilen dosyanin ozeti uyusmuyor; guvenlik icin durduruldu."
        rm -f .nodus_tools/uv.tar.gz .nodus_tools/uv.tar.gz.sha256
        exit 1
    fi
    tar -xzf .nodus_tools/uv.tar.gz -C .nodus_tools --strip-components=1 || { echo "[HATA] uv acilamadi."; exit 1; }
    rm -f .nodus_tools/uv.tar.gz .nodus_tools/uv.tar.gz.sha256
    export UV_PYTHON_INSTALL_DIR="$PWD/.nodus_tools/python" UV_CACHE_DIR="$PWD/.nodus_tools/cache"
    echo "[0/2] Python 3.12 indiriliyor ve sanal ortam hazirlaniyor..."
    rm -rf .venv
    .nodus_tools/uv venv --python 3.12 --seed .venv || { echo "[HATA] Python 3.12 kurulamadi."; exit 1; }
}

PY=""
if [ -n "$PYTHON" ]; then   # kullanici ozellikle belirtti: sessizce degistirme
    command -v "$PYTHON" >/dev/null 2>&1 && "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' \
        || { echo "[HATA] PYTHON=$PYTHON bulunamadi ya da Python 3.12'den eski."; exit 1; }
    PY="$PYTHON"
elif [ -z "$NODUS_FORCE_UV" ]; then
    for c in python3.12 python3.13 python3; do
        if command -v "$c" >/dev/null 2>&1 && py_ok "$c"; then PY="$c"; break; fi
    done
fi

if [ -z "$PY" ]; then
    bootstrap_uv
    PY=".venv/bin/python"
elif [ -z "$NODUS_NO_VENV" ]; then
    # Homebrew/sistem Python'u pip ile dogrudan kurulumu reddeder (PEP 668): bu yuzden .venv
    if [ -d .venv ] && ! .venv/bin/python -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        echo "Eski/bozuk .venv yeniden olusturuluyor..."; rm -rf .venv
    fi
    if [ ! -d .venv ]; then
        echo "[0/2] Sanal ortam (.venv) olusturuluyor..."
        "$PY" -m venv .venv || { echo "[HATA] .venv olusturulamadi."; exit 1; }
    fi
    PY=".venv/bin/python"
fi

# shortcut: damga yalniz .venv icin tutulur; requirements.txt degismediyse pip denetimi atlanir (acilis hizlanir). Elle paket silinirse .venv/.nodus_req silinmeli.
STAMP=""; [ "$PY" = ".venv/bin/python" ] && STAMP=".venv/.nodus_req"
REQ_SUM=$(cksum < requirements.txt)
if [ -n "$STAMP" ] && [ "$(cat "$STAMP" 2>/dev/null)" = "$REQ_SUM" ]; then
    echo "[1/2] Kutuphaneler hazir."
else
    echo "[1/2] Gerekli kutuphaneler denetleniyor (ilk seferde birkac dakika surebilir)..."
    if PIP_OUT=$("$PY" -m pip install -r requirements.txt --quiet --disable-pip-version-check 2>&1); then
        [ -n "$STAMP" ] && echo "$REQ_SUM" > "$STAMP"
    else
        echo "[UYARI] Kutuphane kurulumunda hata (internet yok ya da Python surumu uyumsuz olabilir). Son satirlar:"
        echo "$PIP_OUT" | tail -8
        echo "        Kurulu olanlarla devam ediliyor..."
    fi
fi

echo "[2/2] Nodus penceresi aciliyor... Kapatmak icin Ctrl + C."
exec "$PY" server.py
