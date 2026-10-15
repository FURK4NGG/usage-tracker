#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BASE_DIR="$HOME/.config/usage-tracker"
SYSTEMD_DIR="$HOME/.config/systemd/user"

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

command_exists() {
    command -v "$1" >/dev/null 2>&1
}

install_packages() {
    local pm=""

    if command_exists pacman; then
        pm="pacman"
    elif command_exists apt-get; then
        pm="apt"
    elif command_exists dnf; then
        pm="dnf"
    else
        return 1
    fi

    log "Installing GTK 4, gtk4-layer-shell, PyGObject, and jq dependencies using ${pm}..."

    case "$pm" in
        pacman)
            sudo pacman -S --needed --noconfirm \
                python-gobject \
                gtk4 \
                gtk4-layer-shell \
                jq
            ;;

        apt)
            sudo apt-get update
            sudo apt-get install -y \
                python3-gi \
                gir1.2-gtk-4.0 \
                gir1.2-gtk4layershell-1.0 \
                jq
            ;;

        dnf)
            sudo dnf install -y \
                python3-gobject \
                gtk4 \
                gtk4-layer-shell \
                jq
            ;;
    esac
}

# ---------------------------------------------------------------------------
# Install required packages
# ---------------------------------------------------------------------------

install_packages || error "Unsupported package manager. Please install GTK 4, gtk4-layer-shell, PyGObject, and jq manually."
PYTHON="$(command -v python3 || true)"

# ---------------------------------------------------------------------------
# Basic tool checks
# ---------------------------------------------------------------------------

[[ -n "$PYTHON" ]] || error "python3 was not found."

command -v systemctl >/dev/null 2>&1 \
    || error "systemctl was not found (this tool requires systemd --user services)."

for file in usage-tracker.py usage-widget.py usage-tracker.service; do
    [[ -f "$SCRIPT_DIR/$file" ]] || error "Eksik dosya: $SCRIPT_DIR/$file"
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
    error "PyGObject / GTK 4.0 was not found. Arch: sudo pacman -S python-gobject gtk4 | Debian/Ubuntu: sudo apt install python3-gi gir1.2-gtk-4.0 | Fedora: sudo dnf install python3-gobject gtk4"
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
    warn "'notify-send' was not found. Usage-limit notifications will not be available."
    warn "Arch: sudo pacman -S libnotify | Debian/Ubuntu: sudo apt install libnotify-bin | Fedora: sudo dnf install libnotify"
    warn "A notification daemon (such as mako, dunst, or swaync) must also be running."
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
        log "Compositor: Hyprland (full support)"
        ;;
    sway)
        log "Compositor: Sway (full support)"
        ;;
    wlr-generic)
        log "Compositor: wlroots-based (e.g. River/Wayfire/Hikari/Labwc) - support detected through lswt"
        ;;
    unsupported)
        warn "GNOME veya KDE Plasma (Wayland) tespit edildi."
        warn "These desktops do not expose the Wayland protocol required to track the active window."
        warn "Installation will continue, but the tracker will not be able to identify the focused application."
        ;;
    *)
        warn "Compositor not detected. Outside Hyprland, Sway, or a wlroots compositor with lswt installed,"
        warn "the tracker may not work outside Hyprland, Sway, or a wlroots compositor (River/Wayfire/Hikari/Labwc)."
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
echo "Commands:"
echo "  systemctl --user status usage-tracker.service"
echo "  journalctl --user -u usage-tracker.service -f"
echo
echo "To open the widget, add a shortcut to your compositor configuration, e.g. Hyprland (hyprland.conf):"
echo "  bind = SUPER, U, exec, $PYTHON $BASE_DIR/usage-widget.py"
echo
if [[ "$COMPOSITOR_STATUS" == "unsupported" ]]; then
    echo "NOTE: Active-window tracking is not supported on this desktop (GNOME/KDE Wayland)."
    echo "The service will run, but it will not collect usage data."
    echo
fi
