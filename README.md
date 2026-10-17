## 👀 usage-tracker Overview  

A lightweight application usage tracker for Linux that monitors active application usage and displays daily usage statistics through a GTK4-based widget.  
<br><br>

![usage-tracker Demo Video](https://github.com/FURK4NGG/usage-tracker/blob/main/%7B%7D/usage-tracker.gif)

<br><br>

✅ Works On  
- Linux distributions: Arch Linux, Debian, Fedora  
- Wayland compositors: Hyprland, Sway, and other wlroots-based compositors  

⚠️ Compatibility  
Other Wayland compositors and desktop environments have not been verified yet.
<br><br>

## 🚀 Features

- [x] Measures active application usage time  
- [x] Categorizes applications automatically  
- [x] Generates hourly usage breakdowns  
- [x] Adds customizable reminders for drinking water, coffee breaks, and exercise with automatic notifications  
- [x] Records daily usage history (last 30 days)  
- [x] Stores everything locally in usage-data.json  
- [x] Runs in the background as a systemd --user service  
- [x] Lists the most-used applications  
- [x] Shows total daily usage time  
- [x] Simple bar-graph view of hourly usage  
- [x] Instant English / Turkish language switching  
- [x] Automatically tracks your app usage and notifies you instantly when you reach the time limits you set  

<br>

## 📦 Setup

Directory Structure  
~/.config/usage-tracker/  
├── install.sh  
├── usage-tracker.py  
├── usage-tracker.service  
├── usage-widget.py  
├── habit-timers.json (This file is auto-generated)  
├── usage-widget.lock (This file is auto-generated)  
├── usage-widget-language.json (This file is auto-generated)  
├── usage-limits.json (This file is auto-generated)  
└── usage-data.json (This file is auto-generated)  
<br>


```
git clone https://github.com/FURK4NGG/usage-tracker.git
cd usage-tracker
mkdir -p ~/.config/usage-tracker
cp usage-tracker.py \
   usage-tracker.service \
   usage-widget.py \
   install.sh \
   LICENSE \
   README.md \
   ~/.config/usage-tracker/


chmod +x ~/.config/usage-tracker/usage-widget.py  
chmod +x ~/.config/usage-tracker/usage-tracker.py  
chmod +x ~/.config/usage-tracker/usage-tracker.service  
chmod +x ~/.config/usage-tracker/install.sh  
```


Arch
```
sudo pacman -S python-gobject gtk4 gtk4-layer-shell jq libnotify
```
<br>

<details>
<summary>Debian / Ubuntu</summary>
   
```
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 jq libnotify-bin
```

# Installation on Debian 12 (Bookworm)

This guide explains how to install and run **Usage Tracker** on Debian 12, including Raspberry Pi OS Bookworm on ARM64.

## 1. Install system dependencies

Update the package lists and install the required build tools and libraries:

```bash
sudo apt update
sudo apt install -y \
  git build-essential meson ninja-build pkg-config \
  libgtk-4-dev libwayland-dev wayland-protocols \
  gobject-introspection libgirepository1.0-dev \
  python3-gi valac jq libnotify-bin
```

## 2. Build and install GTK4 Layer Shell

Debian 12 does not provide the required `Gtk4LayerShell` introspection package through its default APT repositories. Build `gtk4-layer-shell` from source instead.

Clone the version used for this installation:

```bash
cd ~
git clone --branch v1.0.4 https://github.com/wmww/gtk4-layer-shell.git
cd gtk4-layer-shell
```

Configure the build:

```bash
meson setup build \
  --prefix=/usr \
  -Dexamples=false \
  -Ddocs=false \
  -Dtests=false \
  -Dsmoke-tests=false \
  -Dvapi=false
```

Compile and install:

```bash
ninja -C build
sudo ninja -C build install
sudo ldconfig
```

The `valac` package is required by the build configuration. The `-Dvapi=false` option disables Vala API generation while preserving GObject Introspection support required by Python.

## 3. Verify GTK4 Layer Shell

Run the following command:

```bash
python3 -c "import gi; gi.require_version('Gtk4LayerShell', '1.0'); from gi.repository import Gtk4LayerShell; print('Gtk4LayerShell OK')"
```

Expected output:

```text
Gtk4LayerShell OK
```

You can also verify GTK4 and GTK4 Layer Shell together:

```bash
python3 -c "import gi; gi.require_version('Gtk', '4.0'); gi.require_version('Gtk4LayerShell', '1.0'); from gi.repository import Gtk, Gtk4LayerShell; print('GTK4 and Gtk4LayerShell OK')"
```

Expected output:

```text
GTK4 and Gtk4LayerShell OK
```

## 4. Install Usage Tracker

Clone the Usage Tracker repository if you have not already downloaded it:

```bash
cd ~
git clone https://github.com/FURK4NGG/usage-tracker.git
cd usage-tracker
```

If the repository is already present, simply enter its directory:

```bash
cd ~/usage-tracker
```

Make the installer executable and run it:

```bash
chmod +x install.sh
./install.sh
```

The installer checks the dependencies, validates the Python files, copies the application files into the configuration directory, and installs the systemd user service.

Installed files:

- Application directory: `~/.config/usage-tracker/`
- Background tracker: `~/.config/usage-tracker/usage-tracker.py`
- Widget: `~/.config/usage-tracker/usage-widget.py`
- Usage data: `~/.config/usage-tracker/usage-data.json`
- systemd service: `~/.config/systemd/user/usage-tracker.service`

## 5. Enable and start the background service

Reload systemd and enable the service:

```bash
systemctl --user daemon-reload
systemctl --user enable --now usage-tracker.service
```

Check the service status:

```bash
systemctl --user status usage-tracker.service
```

The service should show:

```text
Active: active (running)
```

View recent logs:

```bash
journalctl --user -u usage-tracker.service -n 50 --no-pager
```

Follow live logs:

```bash
journalctl --user -u usage-tracker.service -f
```

The background service tracks application usage and handles configured usage-limit and habit reminders.

## 6. Launch the widget

The widget is launched separately from the background service.

Run it manually:

```bash
/usr/bin/python3 ~/.config/usage-tracker/usage-widget.py
```

To open it using a keyboard shortcut, configure the appropriate shortcut in your desktop compositor.

For example, in Hyprland:

```ini
bind = SUPER, U, exec, /usr/bin/python3 /home/USER/.config/usage-tracker/usage-widget.py
```

Replace `USER` with your Linux username.

## 7. Compositor compatibility

The installer checks whether it can identify a supported compositor. It may display a warning such as:

```text
WARNING: Could not detect a supported compositor.
```

This warning does not necessarily prevent the background service from running. However, correct application tracking and widget positioning depend on the compositor and its supported interfaces.

The installation described here was completed on Raspberry Pi OS / Debian 12 Bookworm with ARM64 architecture. The service started successfully and the GTK4 Layer Shell Python import test passed.

## 8. Useful commands

| Task | Command |
|---|---|
| Start service | `systemctl --user start usage-tracker.service` |
| Stop service | `systemctl --user stop usage-tracker.service` |
| Restart service | `systemctl --user restart usage-tracker.service` |
| Check status | `systemctl --user status usage-tracker.service` |
| View logs | `journalctl --user -u usage-tracker.service -f` |
| Launch widget | `/usr/bin/python3 ~/.config/usage-tracker/usage-widget.py` |

## Notes

- Do not add Debian 13 repositories to Debian 12 just to obtain `gir1.2-gtk4layershell-1.0`.
- The `gtk4-layer-shell` library is installed system-wide under `/usr`.
- The Usage Tracker application files and service configuration are installed under the current user's home directory.
- Enabling the user service starts it immediately and enables it for subsequent user sessions.
- The widget is separate from the background service and must be launched manually or through a desktop shortcut.

</details>


<br>

Fedora
```
sudo dnf install python3-gobject gtk4 gtk4-layer-shell jq libnotify
```
<br><br>

Enable and start the service  
```
systemctl --user daemon-reload  
systemctl --user enable --now usage-tracker.service  
```

▶️ AUTOMATIC STARTER IN EVERY SESSION  
```
systemctl --user enable --now usage-tracker.service
```
Control:systemctl --user is-enabled usage-tracker.service
>enabled

Control:systemctl --user status usage-tracker.service  
>active (running)  

<br><br><br>
Follow the tracker's logs in real time:  
```
journalctl --user -u usage-tracker.service -f
```

Controlling the Service
Restart it:
```
systemctl --user daemon-reload
systemctl --user restart usage-tracker.service
```
Stop it:
```
systemctl --user stop usage-tracker.service
```
Start it again:
```
systemctl --user start usage-tracker.service
```

## List your available monitors:  
```
hyprctl monitors
```
>Monitor DP-2 (ID 0) Monitor HDMI-A-2 (ID 1)

<br><br>

## 🎉 Run
Launch the widget on a specific monitor by connector name:
```
LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so.0 USAGE_TRACKER_MONITOR=HDMI-A-2 python3 ~/.config/usage-tracker/usage-widget.py
```
The code should run on whichever screen the terminal is currently running on:
```
MONITOR=$(hyprctl -j activeworkspace | python3 -c 'import sys,json; print(json.load(sys.stdin)["monitor"])'); LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so.0 USAGE_TRACKER_MONITOR="$MONITOR" python3 ~/.config/usage-tracker/usage-widget.py
```
<br><br>

## ❓ HOW IT WORKS ❓

Hyprland  
   │  
   ▼  
usage-tracker.py  
   │  
   ▼  
usage-data.json  
   │  
   ▼  
usage-widget.py  
<br>

## [usage-tracker.py]  
- Tracks application usage and records daily usage statistics  
- Uygulama kullanımını takip eder ve günlük kullanım istatistiklerini kaydeder

## [usage-widget.py]  
- Displays application usage statistics, graphs, daily history, and usage limits  
- Uygulama kullanım istatistiklerini, grafikleri, günlük geçmişi ve kullanım limitlerini gösterir

## [usage-data.json]  
- Stores recorded application usage data and daily statistics  
- Kaydedilen uygulama kullanım verilerini ve günlük istatistikleri tutar

## [usage-limits.json]  
- Stores per-application usage time limits  
- Uygulama bazında belirlenen kullanım süresi limitlerini tutar

## [usage-widget-language.json]  
- Stores the selected widget interface language  
- Widget arayüzünde seçilen dili tutar  

## [usage-tracker.service]  
- Runs the application usage tracker automatically as a user systemd service  
- Uygulama kullanım takipçisini kullanıcı systemd servisi olarak otomatik çalıştırır

## [install.sh]  
- Installs and configures the application usage tracker  
- Uygulama kullanım takipçisini kurar ve yapılandırır  
<br>

# Fast Installation  

sudo pacman -Syu git  
git clone https://github.com/FURK4NGG/usage-tracker.git  
cd usage-tracker  
chmod +x install.sh  
./install.sh  

## 🔒 License  
<h1 align="center">📜 GPL-3.0 License</h1>
