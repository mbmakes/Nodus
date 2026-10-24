#!/usr/bin/env bash
# Nodus.app'in asil baslaticisi (macOS). .app icindeki ince betik bunu cagirir; boylece duzeltmeler uygulama ici guncellemeyle gelir.
# Calisiyorsa tarayiciyi acar; degilse anlik bildirim verip Terminal'de baslatir. Ikinci tiklama ikinci pencere acmaz.
DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PORT="${NODUS_PORT:-8765}"
LOCK="${TMPDIR:-/tmp}/nodus_launch.lock"
notify() { osascript -e "display notification \"$1\" with title \"Nodus\"" >/dev/null 2>&1 || true; }

if curl -sf "http://127.0.0.1:$PORT/api/ping" 2>/dev/null | grep -q nodus; then
    rm -f "$LOCK"
    exec open "http://127.0.0.1:$PORT/"
fi

if [ -f "$LOCK" ] && [ $(( $(date +%s) - $(stat -f %m "$LOCK" 2>/dev/null || echo 0) )) -lt 90 ]; then
    notify "Nodus zaten başlatılıyor, birkaç saniye bekle."   # shortcut: 90 sn icinde ikinci tiklama yok sayilir; baslatma coktuyse en fazla 90 sn beklenir
    exit 0
fi
touch "$LOCK"
notify "Nodus başlatılıyor… Pencere birkaç saniye içinde açılacak."

[ -f "$DIR/run_nodus.command" ] || { osascript -e 'display alert "Nodus bulunamadı" message "Kurulum klasörü taşınmış veya silinmiş. Kurulum komutunu Terminal içinde yeniden çalıştır."'; rm -f "$LOCK"; exit 1; }

# Kurulum tamamsa (.venv var) Terminal acmadan arka planda baslat; cikti ~/Library/Logs/Nodus.log'a gider. Ilk kurulumda Terminal acilir (ilerleme gorunsun).
if [ -x "$DIR/.venv/bin/python" ]; then
    LOG="$HOME/Library/Logs/Nodus.log"
    mkdir -p "$(dirname "$LOG")"
    echo "=== $(date '+%Y-%m-%d %H:%M:%S') Nodus baslatiliyor ===" >> "$LOG"
    (cd "$DIR" && NODUS_YES=1 nohup bash run_nodus.sh >> "$LOG" 2>&1 &)
    # Hazir olana kadar bekle (Dock'ta simge ziplar); pencereyi sunucunun kendisi acar. Olmazsa hata goster.
    for _ in $(seq 1 "${NODUS_LAUNCH_WAIT:-90}"); do
        curl -sf "http://127.0.0.1:$PORT/api/ping" 2>/dev/null | grep -q nodus && { rm -f "$LOCK"; exit 0; }
        sleep 1
    done
    rm -f "$LOCK"
    choice=$(osascript -e 'display alert "Nodus açılamadı" message "Başlatma günlüğüne bakabilirsin." buttons {"Kapat", "Günlüğü aç"} default button "Günlüğü aç"' 2>/dev/null)
    case "$choice" in *aç*) open -t "$LOG" ;; esac
    exit 1
fi
exec open -a Terminal "$DIR/run_nodus.command"
