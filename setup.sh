#!/bin/bash
# =============================================================================
# Raspberry Pi Kiosk Setup Script
# Run as your normal user (not root) - it will use sudo where needed.
# =============================================================================
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
INSTALL_DIR="/opt/kiosk"
CONFIG_DIR="/etc/kiosk"
USER="${SUDO_USER:-$USER}"

echo "============================================="
echo "  Raspberry Pi Kiosk Installer"
echo "============================================="
echo ""

# --- Must not run as root directly (we need the real user for autologin) ---
if [ "$(id -u)" -eq 0 ] && [ -z "$SUDO_USER" ]; then
    echo "ERROR: Don't run as root. Run as your normal user:"
    echo "  ./setup.sh"
    exit 1
fi

# --- System packages ---
echo "[1/6] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    xserver-xorg \
    xinit \
    x11-xserver-utils \
    chromium \
    xdotool \
    openbox \
    mosquitto \
    mosquitto-clients \
    python3-pip \
    unclutter

# --- Python dependencies ---
echo "[2/6] Installing Python packages..."
pip3 install --break-system-packages paho-mqtt

# --- Allow X to start from systemd / non-console users ---
echo "[2.5/6] Configuring X permissions..."
sudo usermod -aG tty "$USER"
sudo usermod -aG video "$USER"

# Allow anybody to start X (needed when launching from a systemd service)
sudo mkdir -p /etc/X11
sudo tee /etc/X11/Xwrapper.config > /dev/null << 'XWRAP'
allowed_users=anybody
needs_root_rights=yes
XWRAP

# --- Install kiosk files ---
echo "[3/6] Installing kiosk controller..."
sudo mkdir -p "$INSTALL_DIR"
sudo cp "$SCRIPT_DIR/kiosk_controller.py" "$INSTALL_DIR/"
sudo chmod +x "$INSTALL_DIR/kiosk_controller.py"

# --- Config file ---
echo "[4/6] Setting up configuration..."
sudo mkdir -p "$CONFIG_DIR"
if [ ! -f "$CONFIG_DIR/config.json" ]; then
    sudo cp "$SCRIPT_DIR/config.json" "$CONFIG_DIR/config.json"
    echo "  Created $CONFIG_DIR/config.json - edit this with your settings."
else
    echo "  Config already exists, skipping."
fi

# --- Create the .xinitrc for the user ---
echo "[5/6] Configuring X session..."
cat > "/home/$USER/.xinitrc" << 'XINITRC'
#!/bin/sh

# Disable screen blanking and power management
xset s off
xset -dpms
xset s noblank

# Hide the mouse cursor after 1 second of inactivity
unclutter -idle 1 -root &

# Start openbox (needed so Chromium can go truly fullscreen)
openbox --config-file /home/$USER/.config/openbox/rc.xml &

# Wait for openbox to be ready
sleep 1

# Start the kiosk controller (launches Chromium + MQTT listener)
exec python3 /opt/kiosk/kiosk_controller.py
XINITRC
# Replace $USER in xinitrc since it was written with single-quoted heredoc
sed -i "s|\$USER|$USER|g" "/home/$USER/.xinitrc"
chmod +x "/home/$USER/.xinitrc"

# --- Create openbox config that removes all decorations ---
mkdir -p "/home/$USER/.config/openbox"
cat > "/home/$USER/.config/openbox/rc.xml" << 'OPENBOX'
<?xml version="1.0" encoding="UTF-8"?>
<openbox_config xmlns="http://openbox.org/3.4/rc">
  <applications>
    <application class="*">
      <decor>no</decor>
      <fullscreen>yes</fullscreen>
      <maximized>yes</maximized>
    </application>
  </applications>
  <theme>
    <name>Clearlooks</name>
    <titleLayout></titleLayout>
    <keepBorder>no</keepBorder>
    <font place="ActiveWindow"><name>sans</name><size>8</size></font>
  </theme>
  <desktops><number>1</number></desktops>
  <resize><drawContents>yes</drawContents></resize>
  <margins>
    <top>0</top>
    <bottom>0</bottom>
    <left>0</left>
    <right>0</right>
  </margins>
</openbox_config>
OPENBOX

# --- Systemd service to auto-start X + kiosk on boot ---
echo "[6/6] Creating systemd service..."

# Disable getty on tty1 so it doesn't fight with our X server
sudo systemctl disable getty@tty1.service 2>/dev/null || true
sudo systemctl mask getty@tty1.service

sudo tee /etc/systemd/system/kiosk.service > /dev/null << EOF
[Unit]
Description=Kiosk Display (X + Chromium + MQTT)
After=network-online.target mosquitto.service multi-user.target systemd-logind.service
Wants=network-online.target
Conflicts=getty@tty1.service

[Service]
Type=simple
User=$USER
TTYPath=/dev/tty1
StandardInput=tty
StandardOutput=journal
StandardError=journal
SyslogIdentifier=kiosk
Environment=XDG_RUNTIME_DIR=/run/user/$(id -u $USER)
PAMName=login
UtmpIdentifier=tty1

# Wait a few seconds for display hardware and network to settle
ExecStartPre=/bin/sleep 5
ExecStartPre=/bin/chvt 1
ExecStart=/usr/bin/startx /home/$USER/.xinitrc -- :0 vt1 -nocursor -keeptty

Restart=always
RestartSec=10
TimeoutStartSec=60
StartLimitIntervalSec=120
StartLimitBurst=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable kiosk.service

echo ""
echo "============================================="
echo "  Setup complete!"
echo "============================================="
echo ""
echo "  Config file:  $CONFIG_DIR/config.json"
echo "  Edit it to set your MQTT broker and webpage URL."
echo ""
echo "  MQTT Topics:"
echo "    kiosk/refresh     -> send anything to refresh the page"
echo "    kiosk/screen      -> send 'on' or 'off'"
echo "    kiosk/url          -> send a new URL to navigate to"
echo "    kiosk/status       -> request current status"
echo "    kiosk/reboot       -> reboot the Pi"
echo ""
echo "  Quick test (after reboot):"
echo "    mosquitto_pub -t kiosk/refresh -m go"
echo "    mosquitto_pub -t kiosk/screen -m off"
echo "    mosquitto_pub -t kiosk/screen -m on"
echo "    mosquitto_pub -t kiosk/url -m 'https://google.com'"
echo ""
echo "  Start now with:  sudo systemctl start kiosk"
echo "  Or just reboot:  sudo reboot"
echo ""
