#!/usr/bin/env bash
# Nodus tek satirlik kurulum (macOS / Linux):
#   curl -fsSL https://raw.githubusercontent.com/mbmakes/Nodus/master/install.sh | bash
# Son surumu ~/Nodus klasorune indirir ve baslatir. Ortam: NODUS_HOME (hedef klasor), NODUS_ARCHIVE_REF (belirli etiket/dal/commit; test icin)
set -euo pipefail
REPO="mbmakes/Nodus"
DEST="${NODUS_HOME:-$HOME/Nodus}"

echo "==================================================="
echo "                 NODUS KURULUYOR"
echo "==================================================="

if [ -f "$DEST/version.py" ]; then
    echo "Nodus zaten kurulu: $DEST  (guncellemeler uygulamanin icinden gelir)"
else
    for tool in curl unzip; do
        command -v "$tool" >/dev/null 2>&1 || { echo "[HATA] '$tool' bulunamadi; once kur (Linux: sudo apt install $tool)."; exit 1; }
    done
    REF="${NODUS_ARCHIVE_REF:-}"
    if [ -z "$REF" ]; then
        # en yeni (on-surum dahil) surum; eski platforma ozel etiketler (-macos vb.) atlanir
        REF=$(curl -fsSL "https://api.github.com/repos/$REPO/releases?per_page=15" \
            | grep -o '"tag_name": *"[^"]*"' | sed 's/.*: *"\(.*\)"/\1/' | grep -v -E -- '-(macos|windows|linux)$' | head -1) || true
        [ -n "$REF" ] || { echo "[HATA] Surum bilgisi alinamadi (internet baglantisini kontrol et)."; exit 1; }
    fi
    echo "Surum indiriliyor: $REF"
    TMP=$(mktemp -d)
    trap 'rm -rf "$TMP"' EXIT
    curl -fsSL "https://github.com/$REPO/archive/$REF.zip" -o "$TMP/nodus.zip" \
        || curl -fsSL "https://github.com/$REPO/archive/refs/tags/$REF.zip" -o "$TMP/nodus.zip" \
        || { echo "[HATA] Indirme basarisiz: $REF"; exit 1; }
    unzip -q "$TMP/nodus.zip" -d "$TMP/x"
    SRC=$(find "$TMP/x" -mindepth 1 -maxdepth 1 -type d | head -1)
    [ -f "$SRC/version.py" ] || { echo "[HATA] Arsiv beklenen icerikte degil."; exit 1; }
    mkdir -p "$(dirname "$DEST")"
    mv "$SRC" "$DEST"
    chmod +x "$DEST/run_nodus.sh" "$DEST/run_nodus.command" 2>/dev/null || true
    echo "Kuruldu: $DEST"
fi

cd "$DEST"
if [ -r /dev/tty ] && [ -z "${NODUS_YES:-}" ]; then
    exec bash run_nodus.sh < /dev/tty     # 'curl | bash' iken stdin boru; soru sorabilmek icin terminali ver
fi
exec bash run_nodus.sh
