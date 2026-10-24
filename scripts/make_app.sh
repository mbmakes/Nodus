#!/usr/bin/env bash
# macOS: Nodus.app olusturur (Launchpad/Dock/Spotlight'ta gorunur). Bu Mac'te uretildigi icin indirilmis dosya sayilmaz: Gatekeeper uyarisi cikmaz.
# Ortam: NODUS_APP_DIR (hedef klasor, varsayilan ~/Applications). Kullanim: bash scripts/make_app.sh
set -euo pipefail
[ "$(uname -s)" = "Darwin" ] || [ -n "${NODUS_APP_FORCE:-}" ] || { echo "Nodus.app yalniz macOS icindir."; exit 0; }
DIR="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${NODUS_APP_DIR:-$HOME/Applications}"
APP="$OUT/Nodus.app"
VER=$(sed -n 's/^__version__ *= *"\(.*\)"/\1/p' "$DIR/version.py")
[ -d "$APP" ] && rm -r "$APP"   # eski surumun uzerine yaz
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
[ -f "$DIR/assets/Nodus.icns" ] && cp "$DIR/assets/Nodus.icns" "$APP/Contents/Resources/Nodus.icns"

# Baslatici ince tutulur: asil mantik kurulum klasorundeki scripts/app_launch.sh'te (guncellemeyle yenilenir).
cat > "$APP/Contents/MacOS/Nodus" <<L
#!/bin/bash
DIR="$DIR"
[ -f "\$DIR/scripts/app_launch.sh" ] || { osascript -e 'display alert "Nodus bulunamadi" message "Kurulum klasoru tasinmis veya silinmis. Kurulum komutunu Terminal icinde yeniden calistir."'; exit 1; }
exec bash "\$DIR/scripts/app_launch.sh" "\$DIR"
L
chmod +x "$APP/Contents/MacOS/Nodus" "$DIR/run_nodus.command" "$DIR/run_nodus.sh" 2>/dev/null || true

cat > "$APP/Contents/Info.plist" <<P
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleName</key><string>Nodus</string>
<key>CFBundleDisplayName</key><string>Nodus</string>
<key>CFBundleIdentifier</key><string>com.mbmakes.nodus</string>
<key>CFBundleExecutable</key><string>Nodus</string>
<key>CFBundleIconFile</key><string>Nodus</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleVersion</key><string>${VER:-1}</string>
<key>CFBundleShortVersionString</key><string>${VER:-1}</string>
<key>LSMinimumSystemVersion</key><string>10.13</string>
<key>NSHighResolutionCapable</key><true/>
</dict></plist>
P
touch "$APP" 2>/dev/null || true   # Finder simgeyi yeniden okusun
echo "Uygulama olusturuldu: $APP"

# Dock: zaten ekliyse dokunma; NODUS_DOCK=1 sormadan ekler, NODUS_NO_DOCK=1 atlar. Terminal yoksa (CI, NODUS_YES) sormaz ve eklemez.
dock_add() {
    [ -z "${NODUS_NO_DOCK:-}" ] && command -v defaults >/dev/null 2>&1 || return 0
    defaults read com.apple.dock persistent-apps 2>/dev/null | grep -q "Nodus.app" && return 0
    if [ -z "${NODUS_DOCK:-}" ]; then
        { [ -z "${NODUS_YES:-}" ] && [ -r /dev/tty ]; } || return 0
        read -r -p "Nodus Dock'a eklensin mi? [E/h] " ans < /dev/tty || return 0
        case "$ans" in [hHnN]*) return 0 ;; esac
    fi
    defaults write com.apple.dock persistent-apps -array-add \
        "<dict><key>tile-data</key><dict><key>file-data</key><dict><key>_CFURLString</key><string>$APP</string><key>_CFURLStringType</key><integer>0</integer></dict></dict></dict>" \
        && killall Dock && echo "Dock'a eklendi."
}
dock_add || true
