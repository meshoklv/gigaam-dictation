#!/bin/zsh
# Собирает GigaAM.app в корне проекта (иконка + бандл с лаунчером).
set -e
cd "$(dirname "$0")"
PY=.venv/bin/python

# 1) иконка
$PY app/make_icon.py
mkdir -p build/AppIcon.iconset
for spec in "16 icon_16x16" "32 icon_16x16@2x" "32 icon_32x32" "64 icon_32x32@2x" \
            "128 icon_128x128" "256 icon_128x128@2x" "256 icon_256x256" \
            "512 icon_256x256@2x" "512 icon_512x512" "1024 icon_512x512@2x"; do
  size=${spec%% *}
  name=${spec#* }
  sips -z $size $size build/icon_1024.png --out build/AppIcon.iconset/$name.png >/dev/null
done

# 2) бандл
mkdir -p GigaAM.app/Contents/MacOS GigaAM.app/Contents/Resources
iconutil -c icns build/AppIcon.iconset -o GigaAM.app/Contents/Resources/AppIcon.icns

cat > GigaAM.app/Contents/Info.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>              <string>GigaAM</string>
  <key>CFBundleDisplayName</key>       <string>GigaAM</string>
  <key>CFBundleIdentifier</key>        <string>com.example.gigaam-dictation</string>
  <key>CFBundleVersion</key>           <string>1.0</string>
  <key>CFBundleShortVersionString</key><string>1.0</string>
  <key>CFBundleExecutable</key>        <string>GigaAM</string>
  <key>CFBundlePackageType</key>       <string>APPL</string>
  <key>CFBundleIconFile</key>          <string>AppIcon</string>
  <key>LSUIElement</key>               <true/>
  <key>LSMinimumSystemVersion</key>    <string>13.0</string>
  <key>NSHighResolutionCapable</key>   <true/>
  <key>NSMicrophoneUsageDescription</key>
  <string>GigaAM слушает микрофон, пока идёт диктовка (правая ⌘), и расшифровывает голос локально, без интернета.</string>
  <key>NSAppleEventsUsageDescription</key>
  <string>GigaAM проверяет и включает автозапуск в системных настройках.</string>
</dict>
</plist>
PLIST

cat > GigaAM.app/Contents/MacOS/GigaAM <<'LAUNCH'
#!/bin/zsh
export PATH="/opt/homebrew/bin:$PATH"
DIR="$(cd "$(dirname "$0")/../../.." && pwd)"
exec "$DIR/.venv/bin/python" "$DIR/app/main.py"
LAUNCH
chmod +x GigaAM.app/Contents/MacOS/GigaAM

echo "OK: $(pwd)/GigaAM.app"
