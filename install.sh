#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$HOME/.config/usage-tracker"
SYSTEMD_DIR="$HOME/.config/systemd/user"
PYTHON="$(command -v python3 || true)"

log() {
    echo "[usage-tracker] $1"
}

warn() {
    echo "[usage-tracker] WARNING: $1"
}

error() {
    echo "[usage-tracker] ERROR: $1"
    exit 1
}

# ---------------------------------------------------------------------------
# Basic tool checks
# ---------------------------------------------------------------------------

[[ -n "$PYTHON" ]] || error "python3 was not found"

command -v systemctl >/dev/null 2>&1 \
    || error "systemctl was not found (this installer requires systemd --user services)"

for file in usage-tracker.py usage-widget.py usage-tracker.service; do
    [[ -f "$SCRIPT_DIR/$file" ]] || error "Missing file: $SCRIPT_DIR/$file"
done

# ---------------------------------------------------------------------------
# Widget dependencies: PyGObject + GTK 4 + gtk4-layer-shell.
# If any of these are missing, usage-widget.py fails the moment it's
# launched -- easier to catch that now than after the user binds a hotkey
# to a broken command.
# ---------------------------------------------------------------------------

log "Checking widget dependencies (PyGObject, GTK4, gtk4-layer-shell)"

if ! "$PYTHON" -c "
import sys
try:
    import gi
    gi.require_version('Gtk', '4.0')
    from gi.repository import Gtk
except Exception as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
" 2>/tmp/usage-tracker-gtk-check.log; then
    cat /tmp/usage-tracker-gtk-check.log >&2
    error "PyGObject / GTK 4.0 not found. Arch: sudo pacman -S python-gobject gtk4 | Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 | Fedora: sudo dnf install python3-gobject gtk4"
fi

if ! "$PYTHON" -c "
import sys
try:
    import gi
    gi.require_version('Gtk4LayerShell', '1.0')
    from gi.repository import Gtk4LayerShell
except Exception as exc:
    print(exc, file=sys.stderr)
    sys.exit(1)
" 2>/tmp/usage-tracker-layershell-check.log; then
    cat /tmp/usage-tracker-layershell-check.log >&2
    error "gtk4-layer-shell was not found. Arch: sudo pacman -S gtk4-layer-shell | Debian/Ubuntu (recent versions): sudo apt install gir1.2-gtk4layershell-1.0 | Fedora: sudo dnf install gtk4-layer-shell"
fi

rm -f /tmp/usage-tracker-gtk-check.log /tmp/usage-tracker-layershell-check.log

if ! command -v notify-send >/dev/null 2>&1; then
    warn "'notify-send' was not found. Application usage-limit notifications will not be available."
    warn "Arch: sudo pacman -S libnotify | Debian/Ubuntu: sudo apt install libnotify-bin | Fedora: sudo dnf install libnotify"
    warn "A notification server (such as mako, dunst, or swaync) must also be running."
fi

# ---------------------------------------------------------------------------
# Compositor support check (informational, non-fatal).
# ---------------------------------------------------------------------------

log "Checking compositor support"

COMPOSITOR_STATUS="unknown"
if [[ -n "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]] && command -v hyprctl >/dev/null 2>&1; then
    COMPOSITOR_STATUS="hyprland"
elif [[ -n "${SWAYSOCK:-}" ]] && command -v swaymsg >/dev/null 2>&1; then
    COMPOSITOR_STATUS="sway"
elif command -v lswt >/dev/null 2>&1; then
    COMPOSITOR_STATUS="wlr-generic"
elif [[ "${XDG_CURRENT_DESKTOP:-}" =~ GNOME|KDE ]]; then
    COMPOSITOR_STATUS="unsupported"
fi

case "$COMPOSITOR_STATUS" in
    hyprland)
        log "Compositor: Hyprland (fully supported)"
        ;;
    sway)
        log "Compositor: Sway (fully supported)"
        ;;
    wlr-generic)
        log "Compositor: wlroots-based (River/Wayfire/Hikari/Labwc, etc.) - supported via lswt"
        ;;
    unsupported)
        warn "GNOME or KDE Plasma (Wayland) detected."
        warn "These desktops do not expose the Wayland protocol required to track the focused window."
        warn "Installation will continue, but the tracker will not be able to identify the focused application."
        ;;
    *)
        warn "Could not detect a supported compositor. Tracking may not work outside Hyprland, Sway, or a wlroots-based compositor with lswt installed."
        warn "If you use a wlroots-based compositor, try installing the 'lswt' package."
        ;;
esac

# ---------------------------------------------------------------------------
# Install
# ---------------------------------------------------------------------------

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
echo "Tracker (background service):"
echo "  $BASE_DIR/usage-tracker.py"
echo
echo "Widget (launched manually with a shortcut; not a service):"
echo "  $PYTHON $BASE_DIR/usage-widget.py"
echo
echo "Data:"
echo "  $BASE_DIR/usage-data.json"
echo
echo "Service:"
echo "  $SYSTEMD_DIR/usage-tracker.service"
echo
echo "Status and logs:"
echo "  systemctl --user status usage-tracker.service"
echo "  journalctl --user -u usage-tracker.service -f"
echo
echo "To open the widget, add a shortcut to your compositor configuration, for example in Hyprland (hyprland.conf):"
echo "  bind = SUPER, U, exec, $PYTHON $BASE_DIR/usage-widget.py"
echo
if [[ "$COMPOSITOR_STATUS" == "unsupported" ]]; then
    echo "NOTE: Focused-window tracking is not supported on this desktop (GNOME/KDE Wayland); "
    echo "the service will run but will not collect usage data."
    echo
fi
