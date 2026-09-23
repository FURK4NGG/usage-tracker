#!/usr/bin/env python3
import json
import os
import re
import select
import socket
import subprocess
import time
from datetime import datetime

BASE_DIR = os.path.expanduser("~/.config/usage-tracker")
DATA_FILE = os.path.join(BASE_DIR, "usage-data.json")
POLL_INTERVAL = 1.0
MAX_DAYS = 30
MAX_SEGMENT = 5.0

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


def active_window():
    try:
        p = subprocess.run(
            ["hyprctl", "-j", "activewindow"],
            capture_output=True,
            text=True,
            timeout=1.5
        )
        if p.returncode != 0:
            return None
        return json.loads(p.stdout)
    except Exception:
        return None


def application_from_window(window):
    if not isinstance(window, dict):
        return None
    app = window.get("class") or window.get("initialClass")
    if not app:
        return None
    return str(app).strip().lower() or None


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
    print(f"[usage-tracker] Data: {DATA_FILE}", flush=True)

    data = load_data()
    event_sock = open_event_socket()

    current_app = application_from_window(active_window())
    last_time = time.time()
    last_save = 0.0

    while True:
        now = time.time()

        # Prefer event-driven active-window updates, with polling as fallback.
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
            polled = application_from_window(active_window())
            if polled:
                current_app = polled

        elapsed = min(now - last_time, MAX_SEGMENT)

        if current_app and not session_locked():
            record_usage(data, current_app, now - elapsed, elapsed)

        last_time = now

        if now - last_save >= 1:
            cleanup(data)
            save_data(data)
            last_save = now

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
