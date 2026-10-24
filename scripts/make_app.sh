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

# Baslatici: Nodus zaten calisiyorsa yalniz tarayiciyi acar; degilse Terminal'de run_nodus.command'i baslatir (kurulum ilerlemesi ve hatalar gorunur).
cat > "$APP/Contents/MacOS/Nodus" <<L
#!/bin/bash
DIR="$DIR"
PORT="\${NODUS_PORT:-8765}"
if curl -sf "http://127.0.0.1:\$PORT/api/ping" 2>/dev/null | grep -q nodus; then
    exec open "http://127.0.0.1:\$PORT/"
fi
[ -f "\$DIR/run_nodus.command" ] || { osascript -e 'display alert "Nodus bulunamadi" message "Kurulum klasoru tasinmis veya silinmis. Kurulum komutunu Terminal icinde yeniden calistir."'; exit 1; }
exec open -a Terminal "\$DIR/run_nodus.command"
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
