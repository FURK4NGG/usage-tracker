## 👀 usage-tracker Overview  

A simple application usage tracker for Hyprland that monitors active application usage and displays daily usage statistics through a GTK4-based widget.  

✅ Works On  
wlroots-based Wayland compositors (Hyprland, Sway, River, Wayfire, Hikari, Labwc)  

❌ Not Supported  
GNOME (Wayland), KDE Plasma (Wayland) — neither exposes the toplevel-list
protocol this tool relies on to see which window is focused


Directory Structure  
~/.config/usage-tracker/  
├── install.sh  
├── usage-tracker.py  
├── usage-widget.py  
├── usage-tracker.service  
├── usage-widget.lock (This file is auto-generated)  
├── usage-widget-language.json (This file is auto-generated)  
└── usage-data.json (This file is auto-generated)  


## 🚀 Features

- [x] Measures active application usage time  
- [x] Categorizes applications automatically  
- [x] Generates hourly usage breakdowns  
- [x] Records daily usage history (last 30 days)  
- [x] Stores everything locally in usage-data.json  
- [x] Runs in the background as a systemd --user service  
- [x] Lists the most-used applications  
- [x] Shows total daily usage time  
- [x] Simple bar-graph view of hourly usage  
- [x] Instant English / Turkish language switching  
- [ ] App sinirlandirma   

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



## 📦 Setup

```
git clone https://github.com/FURK4NGG/usage-tracker.git
cd usage-tracker
mkdir -p ~/.config/usage-tracker
cp usage-data.json \
   usage-tracker.py \
   usage-tracker.service \
   usage-widget.py \
   install.sh \
   LICENSE \
   README.md \
   ~/.config/usage-tracker/
```

chmod +x ~/.config/usage-tracker/usage-widget.py  
chmod +x ~/.config/usage-tracker/usage-tracker.py  
chmod +x ~/.config/usage-tracker/usage-tracker.service  
chmod +x ~/.config/usage-tracker/install.sh  

Arch
```
sudo pacman -S python-gobject gtk4 gtk4-layer-shell jq
```
Debian / Ubuntu
```
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-gtk4layershell-1.0 jq
```
Fedora
```
sudo dnf install python3-gobject gtk4 gtk4-layer-shell jq
```


Enable and start the service  
systemctl --user daemon-reload  
systemctl --user enable --now usage-tracker.service  

▶️ AUTOMATIC STARTER  
systemctl --user enable usage-tracker.service
Control:systemctl --user is-enabled usage-tracker.service
>enabled

Control:systemctl --user status usage-tracker.service  
>active (running)  


## Follow the tracker's logs in real time:  
```
journalctl --user -u usage-tracker.service -f
```

Controlling the Service
Restart it:
```
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
>Monitor DP-1 (ID 0) Monitor HDMI-A-1 (ID 1)

## 🎉 Run
```
python3 ~/.config/usage-tracker/usage-tracker.py
```
or  

Launch the widget on a specific monitor by connector name:
```
USAGE_TRACKER_MONITOR=DP-1 python3 ~/.config/usage-tracker/usage-widget.py
```
The code should run on whichever screen the terminal is currently running on:
```
MONITOR=$(hyprctl -j activeworkspace | python3 -c 'import sys,json; print(json.load(sys.stdin)["monitor"])'); LD_PRELOAD=/usr/lib/libgtk4-layer-shell.so.0 USAGE_TRACKER_MONITOR="$MONITOR" python3 ~/.config/usage-tracker/usage-widget.py
```

# Fast Installation  

sudo pacman -Syu git
git clone https://github.com/FURK4NGG/usage-tracker.git
cd usage-tracker
chmod +x install.sh
./install.sh
