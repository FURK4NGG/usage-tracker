#!/usr/bin/env python3
import json
import os
import signal
import sys
from datetime import datetime

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
TARGET_MONITOR = os.environ.get("USAGE_TRACKER_MONITOR", "").strip()


def load_today():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        today = datetime.now().strftime("%Y-%m-%d")
        return data.get("days", {}).get(today, {
            "total_seconds": 0,
            "applications": {},
            "hourly": {f"{h:02d}": 0 for h in range(24)}
        })
    except Exception:
        return {
            "total_seconds": 0,
            "applications": {},
            "hourly": {f"{h:02d}": 0 for h in range(24)}
        }


def duration(seconds):
    seconds = int(max(0, seconds))
    h, rem = divmod(seconds, 3600)
    m = rem // 60
    if h:
        return f"{h}sa {m}d"
    return f"{m}d"


def graph(hourly):
    values = [float(hourly.get(f"{h:02d}", 0)) for h in range(24)]
    groups = [sum(values[i:i + 2]) for i in range(0, 24, 2)]
    maximum = max(groups, default=0)

    if maximum <= 0:
        return "Kullanım verisi henüz yok."

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
        super().__init__(application=app, title="Application Usage")

        Gtk4LayerShell.init_for_window(self)
        Gtk4LayerShell.set_namespace(self, "usage-tracker")
        Gtk4LayerShell.set_layer(self, Gtk4LayerShell.Layer.OVERLAY)
        Gtk4LayerShell.set_exclusive_zone(self, 0)
        Gtk4LayerShell.set_keyboard_mode(
            self, Gtk4LayerShell.KeyboardMode.NONE
        )

        for edge in (
            Gtk4LayerShell.Edge.TOP,
            Gtk4LayerShell.Edge.BOTTOM,
            Gtk4LayerShell.Edge.LEFT,
            Gtk4LayerShell.Edge.RIGHT,
        ):
            Gtk4LayerShell.set_anchor(self, edge, True)

        self.bind_monitor()
        self.load_css()
        self.build()
        self.refresh()

        GLib.timeout_add_seconds(5, self.refresh)

    def bind_monitor(self):
        if not TARGET_MONITOR:
            return
        try:
            display = self.get_display()
            monitors = display.get_monitors()
            for i in range(monitors.get_n_items()):
                monitor = monitors.get_item(i)
                if monitor.get_connector() == TARGET_MONITOR:
                    Gtk4LayerShell.set_monitor(self, monitor)
                    break
        except Exception as exc:
            print(f"[usage-widget] monitor binding failed: {exc}")

    def load_css(self):
        css = """
        window { background: transparent; }
        .bg { background: rgba(0,0,0,0.28); }
        .card {
            background: rgba(20,20,24,0.92);
            border-radius: 18px;
            padding: 28px 34px;
        }
        .title { color: white; font-size: 25px; font-weight: 700; }
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

        bg = Gtk.Box()
        bg.add_css_class("bg")
        overlay.set_child(bg)

        center = Gtk.CenterBox()
        overlay.add_overlay(center)

        self.card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=14
        )
        self.card.add_css_class("card")
        center.set_center_widget(self.card)

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
        day = load_today()
        apps = day.get("applications", {})
        total = day.get("total_seconds", 0)

        self.clear_card()

        self.add_label("Uygulama Kullanımı", "title")
        self.add_label(
            f"Bugün • {duration(total)}",
            "muted"
        )

        self.add_label(
            graph(day.get("hourly", {})),
            "graph"
        )

        cats = category_totals(apps)[:3]
        cat_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=50
        )

        for name, seconds in cats:
            box = Gtk.Box(
                orientation=Gtk.Orientation.VERTICAL,
                spacing=2
            )
            a = Gtk.Label(label=name)
            a.add_css_class("label")
            a.set_xalign(0)
            b = Gtk.Label(label=duration(seconds))
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

            name = Gtk.Label(label=str(item.get("name", "Unknown")))
            name.add_css_class("label")
            name.set_xalign(0)

            value = Gtk.Label(
                label=duration(item.get("seconds", 0))
            )
            value.add_css_class("value")
            value.set_xalign(0)

            box.append(name)
            box.append(value)
            grid.attach(box, col, row, 1, 1)

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
    app = UsageApp()
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    signal.signal(signal.SIGTERM, lambda *_: app.quit())
    return app.run(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
