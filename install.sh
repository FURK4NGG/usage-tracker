#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$HOME/.config/usage-tracker"
SYSTEMD_DIR="$HOME/.config/systemd/user"
PYTHON="$(command -v python3)"

log() {
    echo "[usage-tracker] $1"
}

error() {
    echo "[usage-tracker] ERROR: $1"
    exit 1
}

[[ -n "$PYTHON" ]] || error "python3 bulunamadı"

for file in usage-tracker.py usage-widget.py usage-tracker.service; do
    [[ -f "$SCRIPT_DIR/$file" ]] || error "Eksik dosya: $SCRIPT_DIR/$file"
done

mkdir -p "$BASE_DIR" "$SYSTEMD_DIR"

log "Installing project into $BASE_DIR"

cp "$SCRIPT_DIR/usage-tracker.py" "$BASE_DIR/usage-tracker.py"
cp "$SCRIPT_DIR/usage-widget.py" "$BASE_DIR/usage-widget.py"

chmod +x "$BASE_DIR/usage-tracker.py"
chmod +x "$BASE_DIR/usage-widget.py"

log "Checking Python syntax"
"$PYTHON" -m py_compile \
    "$BASE_DIR/usage-tracker.py" \
    "$BASE_DIR/usage-widget.py"

sed \
    -e "s|__PYTHON__|$PYTHON|g" \
    -e "s|__BASE_DIR__|$BASE_DIR|g" \
    "$SCRIPT_DIR/usage-tracker.service" \
    > "$SYSTEMD_DIR/usage-tracker.service"

if [[ ! -f "$BASE_DIR/usage-data.json" ]]; then
    cat > "$BASE_DIR/usage-data.json" <<'EOF'
{
  "version": 1,
  "updated_at": "",
  "days": {}
}
EOF
fi

systemctl --user daemon-reload
systemctl --user enable usage-tracker.service
systemctl --user restart usage-tracker.service

echo
echo "=========================================="
echo " Application Usage Tracker"
echo " Installation complete"
echo "=========================================="
echo
echo "Project:"
echo "  $BASE_DIR"
echo
echo "Tracker:"
echo "  $BASE_DIR/usage-tracker.py"
echo
echo "Widget:"
echo "  $BASE_DIR/usage-widget.py"
echo
echo "Data:"
echo "  $BASE_DIR/usage-data.json"
echo
echo "Service:"
echo "  $SYSTEMD_DIR/usage-tracker.service"
echo
echo "Kontrol:"
echo "  systemctl --user status usage-tracker.service"
echo "  journalctl --user -u usage-tracker.service -f"
echo
