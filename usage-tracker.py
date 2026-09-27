#!/usr/bin/env python3
import json
import os
import re
import select
import shutil
import socket
import subprocess
import time
from datetime import datetime

BASE_DIR = os.path.expanduser("~/.config/usage-tracker")
DATA_FILE = os.path.join(BASE_DIR, "usage-data.json")
LANGUAGE_FILE = os.path.join(BASE_DIR, "usage-widget-language.json")
LIMITS_FILE = os.path.join(BASE_DIR, "usage-limits.json")
POLL_INTERVAL = 1.0
MAX_DAYS = 30
MAX_SEGMENT = 5.0

NOTIFY_TITLE = {
    "en": "Usage Tracker",
    "tr": "Kullanım Takipçisi",
}
NOTIFY_TEXT = {
    "en": "{app} usage limit reached",
    "tr": "{app} kullanım limiti doldu",
}

CATEGORY_MAP = {
    "firefox": "Bilgi",
    "google-chrome": "Bilgi",
    "chrome": "Bilgi",
    "chromium": "Bilgi",
    "brave": "Bilgi",
    "microsoft-edge": "Bilgi",
    "code": "Üretkenlik",
    "code-oss": "Üretkenlik",
    "codium": "Üretkenlik",
    "nvim": "Üretkenlik",
    "vim": "Üretkenlik",
    "emacs": "Üretkenlik",
    "foot": "Üretkenlik",
    "kitty": "Üretkenlik",
    "alacritty": "Üretkenlik",
    "wezterm": "Üretkenlik",
    "konsole": "Üretkenlik",
    "gnome-terminal": "Üretkenlik",
    "discord": "İletişim",
    "telegram-desktop": "İletişim",
    "slack": "İletişim",
    "signal": "İletişim",
    "spotify": "Eğlence",
    "mpv": "Eğlence",
    "vlc": "Eğlence",
    "steam": "Oyun",
    "lutris": "Oyun",
    "heroic": "Oyun",
    "thunar": "Sistem",
    "dolphin": "Sistem",
    "nautilus": "Sistem",
    "pcmanfm": "Sistem",
}

DISPLAY_NAMES = {
    "firefox": "Firefox",
    "google-chrome": "Google Chrome",
    "chrome": "Chrome",
    "chromium": "Chromium",
    "brave": "Brave",
    "microsoft-edge": "Microsoft Edge",
    "code": "VS Code",
    "code-oss": "VS Code",
    "codium": "VSCodium",
    "nvim": "Neovim",
    "foot": "Terminal",
    "kitty": "Terminal",
    "alacritty": "Terminal",
    "wezterm": "Terminal",
    "discord": "Discord",
    "telegram-desktop": "Telegram",
    "spotify": "Spotify",
    "steam": "Steam",
    "mpv": "MPV",
    "vlc": "VLC",
    "thunar": "Thunar",
    "dolphin": "Dolphin",
    "nautilus": "Files",
}

os.makedirs(BASE_DIR, exist_ok=True)


def now_iso():
    return datetime.now().replace(microsecond=0).isoformat()


def empty_data():
    return {"version": 1, "updated_at": now_iso(), "days": {}}


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return empty_data()
        data.setdefault("version", 1)
        data.setdefault("updated_at", now_iso())
        data.setdefault("days", {})
        return data
    except (OSError, ValueError, json.JSONDecodeError):
        return empty_data()


def save_data(data):
    data["updated_at"] = now_iso()
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, DATA_FILE)


def ensure_day(data, date):
    day = data["days"].setdefault(date, {
        "total_seconds": 0,
        "applications": {},
        "hourly": {f"{h:02d}": 0 for h in range(24)}
    })
    day.setdefault("total_seconds", 0)
    day.setdefault("applications", {})
    day.setdefault("hourly", {f"{h:02d}": 0 for h in range(24)})
    return day


def record_usage(data, app, start_ts, seconds):
    if not app or seconds <= 0:
        return

    remaining = min(float(seconds), MAX_SEGMENT)
    cursor = float(start_ts)

    while remaining > 0:
        dt = datetime.fromtimestamp(cursor)
        date = dt.strftime("%Y-%m-%d")
        hour = dt.strftime("%H")

        # Never attribute time across an hour boundary incorrectly.
        hour_end = datetime(
            dt.year, dt.month, dt.day, dt.hour, 59, 59, 999999
        ).timestamp() + 0.000001
        chunk = min(remaining, max(0.001, hour_end - cursor))

        day = ensure_day(data, date)
        item = day["applications"].setdefault(app, {
            "name": display_name(app),
            "seconds": 0,
            "category": category(app)
        })

        item["seconds"] += chunk
        day["total_seconds"] += chunk
        day["hourly"][hour] = day["hourly"].get(hour, 0) + chunk

        cursor += chunk
        remaining -= chunk


def cleanup(data):
    dates = sorted(data["days"])
    for date in dates[:-MAX_DAYS]:
        del data["days"][date]


def display_name(app):
    return DISPLAY_NAMES.get(app, app)


def category(app):
    return CATEGORY_MAP.get(app, "Diğer")


def current_language():
    try:
        with open(LANGUAGE_FILE, "r", encoding="utf-8") as f:
            value = json.load(f).get("language", "en")
            if value in ("en", "tr"):
                return value
    except Exception:
        pass
    return "en"


def load_limits():
    """Read the current limits from usage-limits.json."""
    try:
        with open(LIMITS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


_limits_cache = {}
_limits_mtime_ns = None


def get_limits():
    """Return current limits and automatically reload a changed file.

    The widget writes usage-limits.json while this process is running.
    Comparing mtime_ns makes the tracker pick up those changes without
    restarting the systemd service.
    """
    global _limits_cache, _limits_mtime_ns

    try:
        mtime_ns = os.stat(LIMITS_FILE).st_mtime_ns
    except OSError:
        mtime_ns = None

    if mtime_ns != _limits_mtime_ns:
        new_limits = load_limits()

        # Only replace the cache after a successful JSON read. This prevents
        # a transient/partial file write from erasing the active limits.
        if mtime_ns is None:
            _limits_cache = {}
        else:
            _limits_cache = new_limits

        _limits_mtime_ns = mtime_ns
        print(
            f"[usage-tracker] Limits reloaded automatically: "
            f"{len(_limits_cache)} configured",
            flush=True,
        )

    return _limits_cache


def notify_limit_reached(app):
    lang = current_language()
    message = NOTIFY_TEXT.get(lang, NOTIFY_TEXT["en"]).format(
        app=display_name(app)
    )
    title = NOTIFY_TITLE.get(lang, NOTIFY_TITLE["en"])

    notify_send = shutil.which("notify-send")
    if not notify_send:
        print(
            "[usage-tracker] notify-send not found; "
            f"cannot notify for {display_name(app)}",
            flush=True,
        )
        return False

    try:
        result = subprocess.run(
            [
                notify_send,
                "--app-name=Usage Tracker",
                "--urgency=critical",
                "--expire-time=0",
                title,
                message,
            ],
            capture_output=True,
            text=True,
            timeout=5,
            env=os.environ.copy(),
        )
    except Exception as exc:
        print(
            f"[usage-tracker] notification failed for {display_name(app)}: {exc}",
            flush=True,
        )
        return False

    if result.returncode != 0:
        error = (result.stderr or result.stdout or "").strip()
        print(
            f"[usage-tracker] notify-send failed for {display_name(app)}"
            + (f": {error}" if error else ""),
            flush=True,
        )
        return False

    print(
        f"[usage-tracker] LIMIT REACHED: {display_name(app)}",
        flush=True,
    )
    return True


def check_limit(data, app):
    """Check an app against the current limit without requiring a restart.

    If a limit is changed while the tracker is running, the new value is
    immediately used. A changed limit starts a fresh notification state for
    that app. Thus lowering a limit below today's already-recorded usage will
    notify immediately on the next polling cycle.
    """
    limit_seconds = get_limits().get(app, {}).get("limit_seconds")
    if limit_seconds is None:
        return False

    try:
        limit_seconds = int(limit_seconds)
    except (TypeError, ValueError):
        return False

    if limit_seconds <= 0:
        return False

    today = datetime.now().strftime("%Y-%m-%d")
    day = data["days"].get(today)
    if not day:
        return False

    item = day["applications"].get(app)
    if not item:
        return False

    # Keep the limit that was last applied to this day's app record.
    # This lets a changed limit reset notification state without restarting.
    previous_limit = item.get("_limit_seconds")
    if previous_limit != limit_seconds:
        item["_limit_seconds"] = limit_seconds
        item["notified"] = False

    if item.get("notified"):
        return False

    if float(item.get("seconds", 0) or 0) >= limit_seconds:
        if notify_limit_reached(app):
            item["notified"] = True
            return True

    return False


def detect_compositor():
    """
    Work out which wlroots-based compositor we're running under, so we can
    pick the right way to ask "what window is focused right now?".

    - Hyprland has its own hyprctl CLI and an event socket (fastest, and
      lets us react to focus changes instantly instead of polling).
    - Sway (and other swaymsg-IPC-compatible compositors) expose focus
      state through `swaymsg -t get_tree`.
    - Everything else that implements ext-foreign-toplevel-list-v1 or
      wlr-foreign-toplevel-management-unstable-v1 (River, Wayfire, Hikari,
      Labwc, and in fact Sway/Hyprland too) can be queried generically via
      the small `lswt` utility, which speaks those protocols directly
      instead of any compositor-specific IPC.
    """
    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") and shutil.which("hyprctl"):
        return "hyprland"
    if os.environ.get("SWAYSOCK") and shutil.which("swaymsg"):
        return "sway"
    if shutil.which("lswt"):
        return "wlr-generic"
    return None


COMPOSITOR = detect_compositor()


def _active_app_id_hyprland():
    try:
        p = subprocess.run(
            ["hyprctl", "-j", "activewindow"],
            capture_output=True,
            text=True,
            timeout=1.5
        )
        if p.returncode != 0:
            return None
        window = json.loads(p.stdout)
    except Exception:
        return None
    if not isinstance(window, dict):
        return None
    app = window.get("class") or window.get("initialClass")
    if not app:
        return None
    return str(app).strip().lower() or None


def _find_focused_sway_app_id(node):
    if not isinstance(node, dict):
        return None
    if node.get("focused"):
        app_id = node.get("app_id")
        if app_id:
            return str(app_id).strip().lower()
        # XWayland apps under Sway don't have an app_id, only a window class.
        props = node.get("window_properties") or {}
        cls = props.get("class") or props.get("instance")
        if cls:
            return str(cls).strip().lower()
        return None
    for child in (node.get("nodes") or []) + (node.get("floating_nodes") or []):
        found = _find_focused_sway_app_id(child)
        if found:
            return found
    return None


def _active_app_id_sway():
    try:
        p = subprocess.run(
            ["swaymsg", "-t", "get_tree"],
            capture_output=True,
            text=True,
            timeout=1.5
        )
        if p.returncode != 0:
            return None
        tree = json.loads(p.stdout)
    except Exception:
        return None
    return _find_focused_sway_app_id(tree)


def _active_app_id_wlr_generic():
    # lswt talks ext-foreign-toplevel-list-v1 / wlr-foreign-toplevel-management-
    # unstable-v1 directly, so this works on any wlroots compositor
    # (River, Wayfire, Hikari, Labwc, ...) without needing a compositor-
    # specific IPC command.
    try:
        p = subprocess.run(
            ["lswt", "-j"],
            capture_output=True,
            text=True,
            timeout=1.5
        )
        if p.returncode != 0:
            return None
        payload = json.loads(p.stdout)
    except Exception:
        return None

    if isinstance(payload, dict):
        toplevels = payload.get("toplevels") or payload.get("data") or []
    elif isinstance(payload, list):
        toplevels = payload
    else:
        toplevels = []

    for item in toplevels:
        if not isinstance(item, dict):
            continue
        state = item.get("state")
        if isinstance(state, dict):
            activated = bool(state.get("activated"))
        else:
            activated = bool(item.get("activated"))
        if not activated:
            continue
        app_id = item.get("app-id") or item.get("app_id")
        if app_id:
            return str(app_id).strip().lower()
    return None


def active_app_id():
    """Return the lowercased app-id/class of the currently focused window,
    using whichever method fits the detected compositor, with lswt as a
    generic fallback if the preferred method comes up empty."""
    app = None
    if COMPOSITOR == "hyprland":
        app = _active_app_id_hyprland()
    elif COMPOSITOR == "sway":
        app = _active_app_id_sway()
    elif COMPOSITOR == "wlr-generic":
        app = _active_app_id_wlr_generic()

    if not app and COMPOSITOR != "wlr-generic" and shutil.which("lswt"):
        app = _active_app_id_wlr_generic()

    return app


def session_locked():
    # Standalone project: no dependency on Blacklayer/input-activity.
    try:
        p = subprocess.run(
            ["loginctl", "show-session", os.environ.get("XDG_SESSION_ID", ""), "-p", "LockedHint", "--value"],
            capture_output=True,
            text=True,
            timeout=1
        )
        if p.returncode == 0 and p.stdout.strip().lower() == "yes":
            return True
    except Exception:
        pass
    return False


def get_hyprland_socket():
    runtime = os.environ.get("XDG_RUNTIME_DIR")
    instance = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    if not runtime or not instance:
        return None
    path = os.path.join(runtime, "hypr", instance, ".socket2.sock")
    if not os.path.exists(path):
        return None
    return path


def open_event_socket():
    path = get_hyprland_socket()
    if not path:
        return None
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.connect(path)
        s.setblocking(False)
        return s
    except OSError:
        return None


def main():
    print(f"[usage-tracker] Starting")
    print(f"[usage-tracker] Compositor: {COMPOSITOR or 'unknown (no supported tool found)'}")
    print(f"[usage-tracker] Data: {DATA_FILE}", flush=True)

    data = load_data()
    event_sock = open_event_socket() if COMPOSITOR == "hyprland" else None

    current_app = active_app_id()
    last_time = time.time()
    last_save = 0.0

    while True:
        now = time.time()

        # Prefer event-driven active-window updates on Hyprland, with
        # polling as fallback everywhere else (and if the socket drops).
        if event_sock:
            try:
                readable, _, _ = select.select([event_sock], [], [], 0)
                if readable:
                    raw = event_sock.recv(65536)
                    if not raw:
                        event_sock.close()
                        event_sock = None
                    else:
                        for line in raw.decode("utf-8", "replace").splitlines():
                            if line.startswith("activewindow>>"):
                                parts = line.split(">>", 1)[1].split(",", 1)
                                if parts and parts[0]:
                                    current_app = parts[0].strip().lower()
            except (OSError, ValueError):
                try:
                    event_sock.close()
                except Exception:
                    pass
                event_sock = None

        if not event_sock:
            polled = active_app_id()
            if polled:
                current_app = polled

        elapsed = min(now - last_time, MAX_SEGMENT)

        if current_app and not session_locked():
            record_usage(data, current_app, now - elapsed, elapsed)
            if check_limit(data, current_app):
                save_data(data)
                last_save = now

        last_time = now

        if now - last_save >= 1:
            cleanup(data)
            save_data(data)
            last_save = now

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
