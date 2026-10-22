#!/bin/bash
# GigaAM Dictation — one-command installer for macOS.
#   ./install.sh                 venv + dependencies + model + GigaAM.app + LaunchAgent
#   ./install.sh --no-autostart  skip the LaunchAgent
#   ./install.sh --with-torch    also install the PyTorch fallback backend (~2 GB)
#   ./install.sh --python /path/to/python3   use a specific interpreter (3.10+)
set -euo pipefail

LABEL="com.example.gigaam-dictation"
AUTOSTART=1
WITH_TORCH=0
PY_BIN=""

while [ $# -gt 0 ]; do
  case "$1" in
    --no-autostart) AUTOSTART=0 ;;
    --with-torch)   WITH_TORCH=1 ;;
    --python)       PY_BIN="${2:?--python needs a path}"; shift ;;
    -h|--help)      sed -n '2,7p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
  shift
done

cd "$(dirname "$0")"
ROOT="$(pwd)"

[ "$(uname -s)" = "Darwin" ] || { echo "This tool is macOS-only." >&2; exit 1; }

# --- Python 3.10+ ---------------------------------------------------------
pick_python() {
  local c
  for c in "$PY_BIN" python3.13 python3.12 python3.11 python3.10 python3; do
    [ -n "$c" ] || continue
    command -v "$c" >/dev/null 2>&1 || continue
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'; then
      command -v "$c"; return 0
    fi
  done
  return 1
}
PY="$(pick_python)" || {
  echo "Python 3.10+ not found. Install it (e.g. 'brew install python@3.12') and re-run." >&2
  exit 1
}
echo "==> Using $PY ($("$PY" --version))"

# --- venv + dependencies --------------------------------------------------
echo "==> Creating virtualenv in $ROOT/.venv"
"$PY" -m venv .venv
.venv/bin/python -m pip install --upgrade pip wheel >/dev/null
echo "==> Installing dependencies"
.venv/bin/python -m pip install -r requirements.txt
if [ "$WITH_TORCH" = 1 ]; then
  echo "==> Installing PyTorch fallback backend"
  .venv/bin/python -m pip install -r requirements-torch.txt
fi

# --- model (GigaAM v3 e2e CTC, int8 ONNX, ~hundreds of MB, one-time download)
echo "==> Downloading the GigaAM model (one-time, needs internet)"
.venv/bin/python - <<'PYEOF'
import onnx_asr
onnx_asr.load_model("gigaam-v3-e2e-ctc", quantization="int8")
print("model ready")
PYEOF

# --- sample dictionary (never overwrite the user's own) -------------------
DATA_DIR="$HOME/Library/Application Support/GigaAM-Dictation"
mkdir -p "$DATA_DIR"
if [ ! -f "$DATA_DIR/words.json" ]; then
  cp words.example.json "$DATA_DIR/words.json"
  echo "==> Sample dictionary copied to $DATA_DIR/words.json"
fi

# --- app bundle -----------------------------------------------------------
echo "==> Building GigaAM.app"
/bin/zsh ./build_app.sh
APP="$ROOT/GigaAM.app"

# --- LaunchAgent ----------------------------------------------------------
if [ "$AUTOSTART" = 1 ]; then
  AGENT_DIR="$HOME/Library/LaunchAgents"
  PLIST="$AGENT_DIR/$LABEL.plist"
  mkdir -p "$AGENT_DIR"
  sed -e "s|__LABEL__|$LABEL|g" -e "s|__APP_PATH__|$APP|g" \
      launchd/com.example.gigaam-dictation.plist.template > "$PLIST"
  plutil -lint "$PLIST" >/dev/null
  launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
  launchctl bootstrap "gui/$(id -u)" "$PLIST"
  echo "==> LaunchAgent installed: $PLIST (starts GigaAM.app at login)"
else
  echo "==> Autostart skipped (--no-autostart)"
fi

cat <<MSG

Done. Start it with:  open "$APP"
On first run macOS asks for three permissions (grant all three):
  Input Monitoring, Accessibility, Microphone
  (System Settings > Privacy & Security). Restart the app after Input Monitoring.
Do not enable the in-app "launch at login" together with the LaunchAgent.
Uninstall: ./uninstall.sh
MSG
