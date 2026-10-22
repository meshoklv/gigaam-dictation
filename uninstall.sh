#!/bin/bash
# Removes the LaunchAgent, the app bundle and the virtualenv.
#   ./uninstall.sh          keep history/dictionary and the downloaded model
#   ./uninstall.sh --purge  also delete history, dictionary, log and the model cache
set -euo pipefail

LABEL="com.example.gigaam-dictation"
PURGE=0
[ "${1:-}" = "--purge" ] && PURGE=1

cd "$(dirname "$0")"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST"
pkill -f "[G]igaAM.app/Contents/MacOS/GigaAM" 2>/dev/null || true
rm -rf GigaAM.app build .venv
echo "LaunchAgent, GigaAM.app, build/ and .venv removed."

if [ "$PURGE" = 1 ]; then
  rm -rf "$HOME/Library/Application Support/GigaAM-Dictation" \
         "$HOME/.cache/gigaam" \
         "$HOME/.cache/huggingface/hub/models--istupakov--gigaam-v3-onnx"
  echo "History, dictionary, log and model cache removed."
else
  echo "Kept: ~/Library/Application Support/GigaAM-Dictation and the model cache (use --purge to delete)."
fi
