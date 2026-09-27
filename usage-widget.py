#!/usr/bin/env python3
import json
import os
import signal
import sys
import ctypes.util
import cairo
import fcntl
from datetime import datetime, date, timedelta

# gtk4-layer-shell must be loaded before libwayland-client.
# Re-exec once with LD_PRELOAD so layer-shell works reliably.
if not os.environ.get("USAGE_TRACKER_LAYER_SHELL_PRELOADED"):
    layer_shell = ctypes.util.find_library("gtk4-layer-shell") or "/usr/lib/libgtk4-layer-shell.so.0"
    if os.path.exists(layer_shell):
        os.environ["USAGE_TRACKER_LAYER_SHELL_PRELOADED"] = "1"
        current = os.environ.get("LD_PRELOAD", "").split()
        if layer_shell not in current:
            os.environ["LD_PRELOAD"] = " ".join([layer_shell] + current).strip()
        os.execvpe(sys.executable, [sys.executable] + sys.argv, os.environ)

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gtk, Gdk, GLib

try:
    gi.require_version("Gtk4LayerShell", "1.0")
    from gi.repository import Gtk4LayerShell
except Exception as exc:
    print(f"gtk4-layer-shell is required: {exc}", file=sys.stderr)
    sys.exit(1)

BASE_DIR = os.path.expanduser("~/.config/usage-tracker")
DATA_FILE = os.path.join(BASE_DIR, "usage-data.json")
LOCK_FILE = os.path.join(BASE_DIR, "usage-widget.lock")
LANGUAGE_FILE = os.path.join(BASE_DIR, "usage-widget-language.json")
_lock_handle = None

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "tr")

TRANSLATIONS = {
    "en": {
        "title": "Application Usage",
        "today": "Today",
        "yesterday": "Yesterday",
        "tomorrow": "Tomorrow",
        "weekly_average": "Weekly average",
        "no_usage": "No usage data yet.",
        "language": "Language",
        "english": "English",
        "turkish": "Türkçe",
        "unknown": "Unknown",
        "information": "Information",
        "productivity": "Productivity",
        "other": "Other",
        "entertainment": "Entertainment",
        "applications": "Applications",
        "categories": "Categories",
        "total": "Total",
        "usage": "Usage",
        "communication": "Communication",
        "gaming": "Gaming",
        "system": "System",
    },
    "tr": {
        "title": "Uygulama Kullanımı",
        "today": "Bugün",
        "yesterday": "Dün",
        "tomorrow": "Yarın",
        "weekly_average": "Haftalık ortalama",
        "no_usage": "Henüz kullanım verisi yok.",
        "language": "Dil",
        "english": "English",
        "turkish": "Türkçe",
        "unknown": "Bilinmeyen",
        "information": "Bilgi",
        "productivity": "Üretkenlik",
        "other": "Diğer",
        "entertainment": "Eğlence",
        "applications": "Uygulamalar",
        "categories": "Kategoriler",
        "total": "Toplam",
        "usage": "Kullanım",
        "communication": "İletişim",
        "gaming": "Oyun",
        "system": "Sistem",
    },
}

WEEKDAYS = {
    "en": (
        "Monday", "Tuesday", "Wednesday",
        "Thursday", "Friday", "Saturday", "Sunday"
    ),
    "tr": (
        "Pazartesi", "Salı", "Çarşamba",
        "Perşembe", "Cuma", "Cumartesi", "Pazar"
    ),
}


def load_language():
    try:
        with open(LANGUAGE_FILE, "r", encoding="utf-8") as f:
            value = json.load(f).get("language", DEFAULT_LANGUAGE)
            if value in SUPPORTED_LANGUAGES:
                return value
    except Exception:
        pass
    return DEFAULT_LANGUAGE


def save_language(language):
    if language not in SUPPORTED_LANGUAGES:
        return
    os.makedirs(BASE_DIR, exist_ok=True)
    tmp = LANGUAGE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"language": language}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, LANGUAGE_FILE)

def acquire_single_instance():
    global _lock_handle
    try:
        _lock_handle = open(LOCK_FILE, "w", encoding="utf-8")
        fcntl.flock(_lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        _lock_handle.write(str(os.getpid()))
        _lock_handle.flush()
        return True
    except (BlockingIOError, OSError):
        if _lock_handle:
            _lock_handle.close()
            _lock_handle = None
        print("[usage-widget] already running", flush=True)
        return False

TARGET_MONITOR = (
    os.environ.get("USAGE_TRACKER_MONITOR", "").strip()
    or os.environ.get("BLACKLAYER_MONITOR", "").strip()
)


def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"days": {}}


def empty_day():
    return {
        "total_seconds": 0,
        "applications": {},
        "hourly": {f"{h:02d}": 0 for h in range(24)}
    }


def load_day(data, day_value):
    return data.get("days", {}).get(
        day_value.strftime("%Y-%m-%d"),
        empty_day()
    )


def available_dates(data):
    dates = []
    for key in data.get("days", {}):
        try:
            dates.append(datetime.strptime(key, "%Y-%m-%d").date())
        except ValueError:
            pass
    return sorted(dates)


def weekly_average(data, selected_day):
    """Return one shared weekly average based on the latest day reached."""
    monday = selected_day - timedelta(days=selected_day.weekday())
    sunday = monday + timedelta(days=6)

    recorded_days = [
        day_value
        for day_value in available_dates(data)
        if monday <= day_value <= sunday
    ]

    if not recorded_days:
        return 0.0

    latest_day = max(recorded_days)

    # Every calendar day from Monday through latest_day counts.
    # Missing days are included as 0 seconds.
    divisor = (latest_day - monday).days + 1

    total = 0.0
    for offset in range(divisor):
        day_value = monday + timedelta(days=offset)
        total += float(load_day(data, day_value).get("total_seconds", 0))

    return total / divisor
def translate_category(category, language):
    mapping = {
        "Bilgi": "information",
        "Information": "information",
        "Üretkenlik": "productivity",
        "Productivity": "productivity",
        "Diğer": "other",
        "Other": "other",
        "Eğlence": "entertainment",
        "Entertainment": "entertainment",
        "İletişim": "communication",
        "Communication": "communication",
        "Oyun": "gaming",
        "Gaming": "gaming",
        "Sistem": "system",
        "System": "system",
    }
    key = mapping.get(str(category))
    return TRANSLATIONS[language][key] if key else str(category)


def duration(seconds, language="en"):
    seconds = int(max(0, seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60

    if language == "tr":
        if hours and minutes:
            return f"{hours}sa {minutes}dk"
        if hours:
            return f"{hours}sa"
        return f"{minutes}dk"

    if hours and minutes:
        return f"{hours}h {minutes}m"
    if hours:
        return f"{hours}h"
    return f"{minutes}m"
def graph(hourly, no_data_text="No usage data yet."):
    values = [float(hourly.get(f"{h:02d}", 0)) for h in range(24)]
    groups = [sum(values[i:i + 2]) for i in range(0, 24, 2)]
    maximum = max(groups, default=0)

    if maximum <= 0:
        return no_data_text

    height = 6
    bars = [max(1, round(v / maximum * height)) if v > 0 else 0 for v in groups]
    lines = []

    for row in range(height, 0, -1):
        lines.append(" ".join("█" if h >= row else " " for h in bars))

    lines.append("────────────────────────")
    lines.append("00  04  08  12  16  20")
    return "\n".join(lines)


def category_totals(apps):
    result = {}
    for item in apps.values():
        cat = item.get("category", "Diğer")
        result[cat] = result.get(cat, 0) + float(item.get("seconds", 0))
    return sorted(result.items(), key=lambda x: x[1], reverse=True)


class UsageWindow(Gtk.Window):
    def __init__(self, app):
        super().__init__(application=app, title=TRANSLATIONS[load_language()]["title"])

        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_namespace(self, "usage-tracker")
        # Full-monitor overlay, but without reserving layout space.
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_exclusive_zone(self, 0)

        # Keep keyboard focus so Escape can close the overlay.
        # Mouse input is restricted separately to the center card below.
        Gtk4LayerShell.set_keyboard_mode(
            self, Gtk4LayerShell.KeyboardMode.EXCLUSIVE
        )

        self.set_decorated(False)
        self.set_resizable(False)

        key_controller = Gtk.EventControllerKey()
        key_controller.connect("key-pressed", self.on_key_pressed)
        self.add_controller(key_controller)

        # Do NOT anchor the layer surface to any screen edge.
        # The surface keeps only the card's natural size and is positioned
        # by layer-shell in the center of the selected monitor.
        for edge in (
            Gtk4LayerShell.Edge.TOP,
            Gtk4LayerShell.Edge.BOTTOM,
            Gtk4LayerShell.Edge.LEFT,
            Gtk4LayerShell.Edge.RIGHT,
        ):
            Gtk4LayerShell.set_anchor(self, edge, False)
            Gtk4LayerShell.set_margin(self, edge, 0)

        self.selected_date = date.today()
        self.language = load_language()

        self.bind_monitor()
        self.load_css()
        self.build()
        self.refresh()

        GLib.timeout_add_seconds(5, self.refresh)

    def on_key_pressed(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            self.get_application().quit()
            return True
        return False

    def bind_monitor(self):
        """Bind the fullscreen layer surface to the requested monitor.

        Supports both standalone usage (USAGE_TRACKER_MONITOR) and
        external launchers that pass BLACKLAYER_MONITOR. If neither is
        supplied, the widget stays on the compositor's default output.
        """
        if not TARGET_MONITOR:
            print(
                "[usage-widget] no target monitor specified; using default monitor",
                flush=True
            )
            return

        try:
            display = self.get_display()
            if not display:
                return

            monitors = display.get_monitors()
            for i in range(monitors.get_n_items()):
                monitor = monitors.get_item(i)
                try:
                    connector = monitor.get_connector()
                except Exception:
                    connector = None

                if connector == TARGET_MONITOR:
                    Gtk4LayerShell.set_monitor(self, monitor)
                    print(
                        f"[usage-widget] bound to monitor={TARGET_MONITOR}",
                        flush=True
                    )
                    return

            print(
                f"[usage-widget] monitor not found: {TARGET_MONITOR}",
                flush=True
            )

        except Exception as exc:
            print(
                f"[usage-widget] monitor binding failed: {exc}",
                flush=True
            )

    def change_day(self, direction):
        data = load_data()
        dates = available_dates(data)

        if direction < 0:
            candidates = [d for d in dates if d < self.selected_date]
            if candidates:
                self.selected_date = candidates[-1]
        else:
            candidates = [d for d in dates if d > self.selected_date]
            if candidates:
                self.selected_date = candidates[0]

        self.refresh()

    def rebuild_navigation(self, data):
        dates = available_dates(data)

        previous_exists = any(d < self.selected_date for d in dates)
        next_exists = any(d > self.selected_date for d in dates)

        self.prev_button.set_visible(previous_exists)
        self.next_button.set_visible(next_exists)

        today = date.today()
        tr = TRANSLATIONS[self.language]

        if self.selected_date == today:
            label = tr["today"]
        elif self.selected_date == today - timedelta(days=1):
            label = tr["yesterday"]
        elif self.selected_date == today + timedelta(days=1):
            label = tr["tomorrow"]
        else:
            weekday = WEEKDAYS[self.language][self.selected_date.weekday()]
            label = f"{weekday} {self.selected_date.strftime('%d.%m.%Y')}"

        self.day_label.set_text(label)

    def load_css(self):
        css = """
        window {
            background: transparent;
            border: none;
            box-shadow: none;
        }
        .card {
            background: rgba(20,20,24,0.92);
            border-radius: 24px;
            border: none;
            box-shadow: none;
            padding: 28px 34px;
        }
        .title { color: white; font-size: 25px; font-weight: 700; }
        .day { color: rgba(255,255,255,0.72); font-size: 14px; font-weight: 600; }
        .nav-button {
            color: white;
            background: rgba(255,255,255,0.08);
            border: none;
            border-radius: 10px;
            padding: 4px 10px;
            min-width: 34px;
            min-height: 30px;
        }
        .nav-button:hover { background: rgba(255,255,255,0.16); }
        .lang-box {
            background: rgba(255,255,255,0.06);
            border-radius: 10px;
            padding: 2px;
        }
        .lang-button {
            color: rgba(255,255,255,0.55);
            background: transparent;
            border: none;
            border-radius: 8px;
            min-width: 30px;
            min-height: 26px;
            padding: 2px 8px;
            font-size: 12px;
            font-weight: 700;
        }
        .lang-button:hover { background: rgba(255,255,255,0.10); }
        .lang-button.lang-active {
            color: white;
            background: rgba(255,255,255,0.18);
        }
        .muted { color: rgba(255,255,255,0.60); font-size: 13px; }
        .graph {
            color: white;
            font-family: monospace;
            font-size: 15px;
        }
        .label { color: white; font-size: 14px; font-weight: 700; }
        .value { color: rgba(255,255,255,0.72); font-size: 13px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css.encode())
        display = Gdk.Display.get_default()
        if display:
            Gtk.StyleContext.add_provider_for_display(
                display, provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )

    def build(self):
        overlay = Gtk.Overlay()
        self.set_child(overlay)

        # The layer surface is card-sized now, so the card itself is the
        # surface content. There is no fullscreen transparent/black parent.
        self.card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14
        )
        self.card.add_css_class("card")
        overlay.set_child(self.card)

        self.nav_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10
        )
        self.nav_box.set_hexpand(True)

        self.prev_button = Gtk.Button(label="‹")
        self.prev_button.add_css_class("nav-button")
        self.prev_button.connect("clicked", lambda *_: self.change_day(-1))

        self.day_label = Gtk.Label()
        self.day_label.add_css_class("day")
        self.day_label.set_hexpand(True)
        self.day_label.set_xalign(0.5)

        self.next_button = Gtk.Button(label="›")
        self.next_button.add_css_class("nav-button")
        self.next_button.connect("clicked", lambda *_: self.change_day(1))

        self.nav_box.append(self.prev_button)
        self.nav_box.append(self.day_label)
        self.nav_box.append(self.next_button)

        self.header = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=8
        )
        self.header.set_hexpand(True)

        # NOTE: a GtkPopover/MenuButton was used here previously, but popovers
        # need their own xdg_popup grab, which does not reliably receive
        # input on a fullscreen wlr-layer-shell surface that also holds
        # KeyboardMode.EXCLUSIVE (as this window does) -- the menu could open
        # visually while clicks inside it were silently swallowed. Two plain,
        # always-visible buttons on the main surface avoid that entirely and
        # use the exact same click path as the working prev/next buttons.
        self.lang_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=4
        )
        self.lang_box.add_css_class("lang-box")

        self.en_button = Gtk.Button(label="EN")
        self.en_button.add_css_class("lang-button")
        self.en_button.set_tooltip_text("English")
        self.en_button.connect("clicked", self._select_english)
        self.lang_box.append(self.en_button)

        self.tr_button = Gtk.Button(label="TR")
        self.tr_button.add_css_class("lang-button")
        self.tr_button.set_tooltip_text("Türkçe")
        self.tr_button.connect("clicked", self._select_turkish)
        self.lang_box.append(self.tr_button)

        self.update_language_menu()

        self.header.append(self.lang_box)

        self.nav_box.set_hexpand(True)
        self.header.append(self.nav_box)

    def _select_english(self, button):
        self.set_language("en")
        return True

    def _select_turkish(self, button):
        self.set_language("tr")
        return True

    def set_language(self, language):
        if language not in SUPPORTED_LANGUAGES:
            return
        if language == self.language:
            return

        self.language = language
        save_language(language)

        # Rebuild on the next GTK main-loop iteration so the click that
        # triggered this has fully finished being dispatched first.
        GLib.idle_add(self._apply_language_change)

    def _apply_language_change(self):
        self.update_language_menu()
        self.refresh()
        self.queue_resize()
        self.queue_draw()
        return GLib.SOURCE_REMOVE

    def update_language_menu(self):
        # Highlight whichever of the two plain EN/TR buttons is active,
        # rather than relying on any popover state.
        if self.language == "en":
            self.en_button.add_css_class("lang-active")
            self.tr_button.remove_css_class("lang-active")
        else:
            self.tr_button.add_css_class("lang-active")
            self.en_button.remove_css_class("lang-active")

    def clear_card(self):
        child = self.card.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.card.remove(child)
            child = nxt

    def add_label(self, text, css, xalign=0.0):
        label = Gtk.Label(label=text)
        label.add_css_class(css)
        label.set_xalign(xalign)
        self.card.append(label)
        return label

    def refresh(self):
        data = load_data()
        day = load_day(data, self.selected_date)
        apps = day.get("applications", {})
        total = day.get("total_seconds", 0)
        average = weekly_average(data, self.selected_date)

        self.clear_card()
        self.set_title(TRANSLATIONS[self.language]["title"])

        self.rebuild_navigation(data)
        self.card.append(self.header)

        self.update_language_menu()
        self.add_label(TRANSLATIONS[self.language]["title"], "title")

        summary = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=28
        )
        summary.set_halign(Gtk.Align.CENTER)

        weekday_name = WEEKDAYS[self.language][self.selected_date.weekday()]
        today_text = (
            f"{weekday_name} • {duration(total, self.language)}"
        )
        today_label = Gtk.Label(label=today_text)
        today_label.add_css_class("muted")
        summary.append(today_label)

        avg_label = Gtk.Label(
            label=f'{TRANSLATIONS[self.language]["weekly_average"]} • {duration(average, self.language)}'
        )
        avg_label.add_css_class("muted")
        summary.append(avg_label)

        self.card.append(summary)

        self.add_label(
            graph(day.get("hourly", {}), TRANSLATIONS[self.language]["no_usage"]),
            "graph"
        )

        cats = category_totals(apps)[:3]
        if cats:
            cat_box = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=50
            )

            for name, seconds in cats:
                box = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL,
                    spacing=2
                )
                a = Gtk.Label(label=translate_category(name, self.language))
                a.add_css_class("label")
                a.set_xalign(0)
                b = Gtk.Label(label=duration(seconds, self.language))
                b.add_css_class("value")
                b.set_xalign(0)
                box.append(a)
                box.append(b)
                cat_box.append(box)

            self.card.append(cat_box)

        grid = Gtk.Grid()
        grid.set_column_spacing(55)
        grid.set_row_spacing(12)

        ordered = sorted(
            apps.values(),
            key=lambda x: float(x.get("seconds", 0)),
            reverse=True
        )[:9]

        for i, item in enumerate(ordered):
            col = i % 3
            row = i // 3

            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=2
            )

            name = Gtk.Label(label=str(item.get("name", TRANSLATIONS[self.language]["unknown"])))
            name.add_css_class("label")
            name.set_xalign(0)

            value = Gtk.Label(
                label=duration(item.get("seconds", 0), self.language)
            )
            value.add_css_class("value")
            value.set_xalign(0)

            box.append(name)
            box.append(value)
            grid.attach(box, col, row, 1, 1)

        if ordered:
            self.card.append(grid)

        return True



class UsageApp(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id="com.usagetracker.Widget",
            flags=0
        )

    def do_activate(self):
        win = UsageWindow(self)
        win.present()


def main():
    if not acquire_single_instance():
        return 0

    app = UsageApp()
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
