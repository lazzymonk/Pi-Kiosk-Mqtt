# Raspberry Pi Kiosk Controller

Turn a headless Raspberry Pi (Lite OS) into a fullscreen web kiosk, controllable via MQTT. Includes a Home Assistant custom component for single-device integration.

## What it does

- Boots straight into a fullscreen webpage (no desktop environment needed)
- Accepts MQTT commands to **refresh**, **turn screen on/off**, **adjust brightness**, **change URL**, and **reboot**
- Display rotation support (0, 90, 180, 270 degrees) with automatic touchscreen input mapping
- Backlight brightness control (0-255) via MQTT
- Configurable screen-off method: backlight dimming or DPMS signal
- Optional pinch-to-zoom disable for touchscreens
- Auto-publishes status on a configurable interval (CPU, RAM, temperature, disk, uptime)
- Status updates published immediately after every command
- Auto-restarts on crash
- Home Assistant custom component included (single device with all entities)

## Requirements

- Raspberry Pi (any model with HDMI or DSI display)
- Raspberry Pi OS **Lite** (Bookworm or later)
- A display connected via HDMI or DSI ribbon cable
- Network connection (for MQTT and web content)

## Quick Start

```bash
# 1. Copy the project to your Pi
scp -r pi-kiosk/ pi@your-pi-ip:~/

# 2. SSH in and run setup
ssh pi@your-pi-ip
cd ~/pi-kiosk
chmod +x setup.sh
./setup.sh

# 3. Edit the config
sudo nano /etc/kiosk/config.json

# 4. Reboot
sudo reboot
```

## Configuration

Edit `/etc/kiosk/config.json`:

```json
{
    "mqtt_broker": "192.168.1.100",
    "mqtt_port": 1883,
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_topic_prefix": "kiosk",
    "webpage_url": "https://your-dashboard.com",
    "screen_timeout": 0,
    "scale_factor": 1.0,
    "rotation": 0,
    "brightness": 255,
    "screen_off_method": "backlight",
    "status_interval": 60,
    "disable_pinch_zoom": true
}
```

### Config options

| Option | Default | Description |
|---|---|---|
| `mqtt_broker` | `localhost` | MQTT broker address |
| `mqtt_port` | `1883` | MQTT broker port |
| `mqtt_username` | `""` | MQTT username (leave empty for no auth) |
| `mqtt_password` | `""` | MQTT password |
| `mqtt_topic_prefix` | `kiosk` | Prefix for all MQTT topics |
| `webpage_url` | `https://example.com` | URL to display on boot |
| `screen_timeout` | `0` | Screen blank timeout in seconds (0 = never) |
| `scale_factor` | `1.0` | Chromium display scale (try 0.9-1.0 for small screens) |
| `rotation` | `0` | Display rotation: `0`, `90`, `180`, or `270` degrees |
| `brightness` | `255` | Default backlight brightness (0-255) |
| `screen_off_method` | `backlight` | How to turn screen off: `backlight` (dims to 0) or `dpms` (sends display-off signal) |
| `status_interval` | `0` | Auto-publish status every N seconds (0 = manual only via `kiosk/status`) |
| `disable_pinch_zoom` | `true` | Disable pinch-to-zoom and swipe navigation on touchscreens |

You can also use environment variables (they override the config file). Prefix any key with `KIOSK_`, e.g. `KIOSK_MQTT_BROKER`, `KIOSK_WEBPAGE_URL`, `KIOSK_ROTATION`.

### Rotation

Set `"rotation"` to rotate the display. The touchscreen input coordinates are automatically remapped to match using `xinput`. If you're using a touchscreen and `xinput` isn't installed, run `sudo apt install xinput`.

| Value | Orientation |
|---|---|
| `0` | Normal (landscape) |
| `90` | Rotated right (portrait) |
| `180` | Upside down |
| `270` | Rotated left (portrait) |

### Brightness and screen off behaviour

The `"screen_off_method"` option controls what happens when you send `kiosk/screen off`:

- **`"backlight"`** (recommended for Pi touchscreens) - sets the backlight to 0 via `/sys/class/backlight/*/brightness`. Turning the screen back on restores the brightness to the level it was at before being turned off. This is more reliable for DSI-connected displays.
- **`"dpms"`** - sends a DPMS signal to power off the display. Works better with HDMI monitors.

The `"brightness"` option sets the default backlight level on startup.

## MQTT Topics

All topics use the prefix from config (default: `kiosk`).

| Topic | Payload | Action |
|---|---|---|
| `kiosk/refresh` | anything | Refresh the current page |
| `kiosk/screen` | `on` / `off` | Turn display on or off |
| `kiosk/screen` | anything else | Toggle display |
| `kiosk/brightness` | `0`-`255` | Set backlight brightness |
| `kiosk/url` | a URL string | Navigate to new URL |
| `kiosk/status` | anything | Request status report |
| `kiosk/reboot` | anything | Reboot the Pi |

All commands automatically publish an updated status response immediately after executing.

### Status response

Status is published to `kiosk/status/response` as retained JSON:

```json
{
    "online": true,
    "screen": "on",
    "brightness": 255,
    "url": "https://your-dashboard.com",
    "system": {
        "cpu_percent": 12.3,
        "cpu_temp_c": 48.5,
        "ram_total_mb": 1024.0,
        "ram_used_mb": 412.3,
        "ram_percent": 40.3,
        "disk_total_gb": 29.1,
        "disk_used_gb": 4.2,
        "disk_free_gb": 24.9,
        "disk_percent": 14.4,
        "uptime": "2h 34m 12s"
    }
}
```

When the kiosk goes offline, the MQTT last will publishes `"offline"` to this topic.

## Testing with mosquitto

```bash
# Refresh the page
mosquitto_pub -h localhost -t kiosk/refresh -m go

# Turn screen off
mosquitto_pub -h localhost -t kiosk/screen -m off

# Turn screen on
mosquitto_pub -h localhost -t kiosk/screen -m on

# Set brightness to 50%
mosquitto_pub -h localhost -t kiosk/brightness -m 128

# Set brightness to minimum (not off)
mosquitto_pub -h localhost -t kiosk/brightness -m 1

# Change URL
mosquitto_pub -h localhost -t kiosk/url -m "https://google.com"

# Get status
mosquitto_pub -h localhost -t kiosk/status -m "?"
mosquitto_sub -h localhost -t kiosk/status/response -C 1
```

## Home Assistant Custom Component

A custom component is included that creates a single device in Home Assistant with all controls and sensors. This is the recommended way to integrate with Home Assistant (no manual YAML needed).

### Installation

1. Copy the `custom_components/pi_kiosk` folder into your Home Assistant `config/custom_components/` directory
2. Restart Home Assistant
3. Go to **Settings > Devices & Services > Add Integration**
4. Search for **"Pi Kiosk"**
5. Enter a name and the MQTT topic prefix (e.g. `kiosk`)

### Entities created

**Controls:**

| Entity | Type | Description |
|---|---|---|
| Screen | Switch | Turn display on/off |
| Brightness | Number (slider) | Backlight brightness 0-255 |
| URL | Text | Change the displayed webpage |
| Refresh browser | Button | Refresh the current page |
| Reboot | Button | Reboot the Raspberry Pi |
| Request status | Button | Manually request a status update |

**Sensors (diagnostic):**

| Entity | Type | Description |
|---|---|---|
| CPU usage | Sensor (%) | Current CPU usage percentage |
| CPU temperature | Sensor (C) | CPU temperature |
| RAM usage | Sensor (%) | RAM usage percentage |
| RAM used | Sensor (MB) | RAM used in megabytes |
| Disk usage | Sensor (%) | Disk usage percentage |
| Disk free | Sensor (GB) | Free disk space in gigabytes |
| Last boot | Sensor (timestamp) | When the Pi last booted (shown as relative time) |
| Status | Sensor | Online/Offline (always available, even when kiosk is offline) |

### Multiple kiosks

Add the integration multiple times with different topic prefixes. Each gets its own device with its own set of entities.

### Manual YAML (alternative)

If you prefer not to use the custom component, you can configure entities manually in `configuration.yaml`:

```yaml
mqtt:
  button:
    - name: "Kiosk Refresh"
      command_topic: "kiosk/refresh"
      payload_press: "go"

  switch:
    - name: "Kiosk Screen"
      command_topic: "kiosk/screen"
      state_topic: "kiosk/status/response"
      value_template: "{{ value_json.screen }}"
      payload_on: "on"
      payload_off: "off"
      state_on: "on"
      state_off: "off"

  number:
    - name: "Kiosk Brightness"
      command_topic: "kiosk/brightness"
      state_topic: "kiosk/status/response"
      value_template: "{{ value_json.brightness }}"
      min: 0
      max: 255
      step: 1

  sensor:
    - name: "Kiosk CPU Temperature"
      state_topic: "kiosk/status/response"
      value_template: "{{ value_json.system.cpu_temp_c }}"
      unit_of_measurement: "C"

    - name: "Kiosk CPU Usage"
      state_topic: "kiosk/status/response"
      value_template: "{{ value_json.system.cpu_percent }}"
      unit_of_measurement: "%"

    - name: "Kiosk RAM Usage"
      state_topic: "kiosk/status/response"
      value_template: "{{ value_json.system.ram_percent }}"
      unit_of_measurement: "%"

    - name: "Kiosk Disk Free"
      state_topic: "kiosk/status/response"
      value_template: "{{ value_json.system.disk_free_gb }}"
      unit_of_measurement: "GB"

  text:
    - name: "Kiosk URL"
      command_topic: "kiosk/url"
```

## Service Management

```bash
# Check status
sudo systemctl status kiosk

# View logs
journalctl -u kiosk -f

# Restart
sudo systemctl restart kiosk

# Stop
sudo systemctl stop kiosk
```

## Updating

After changing the Python controller:

```bash
sudo cp kiosk_controller.py /opt/kiosk/kiosk_controller.py
sudo systemctl restart kiosk
```

After changing the service file (via `setup.sh`):

```bash
./setup.sh
sudo systemctl daemon-reload
sudo systemctl restart kiosk
```

## Project Structure

```
pi-kiosk/
├── kiosk_controller.py          # Main Python controller
├── setup.sh                     # Installer script
├── config.json                  # Example config
├── README.md
└── custom_components/
    └── pi_kiosk/                # Home Assistant custom component
        ├── __init__.py
        ├── manifest.json
        ├── config_flow.py
        ├── coordinator.py
        ├── const.py
        ├── switch.py
        ├── number.py
        ├── button.py
        ├── text.py
        ├── sensor.py
        ├── strings.json
        ├── translations/en.json
        └── brand/
            ├── icon.png
            ├── icon@2x.png
            ├── logo.png
            └── logo@2x.png
```

## Troubleshooting

**Black screen / no browser**: Check `journalctl -u kiosk -f` for errors. Make sure your user has permission to start X (`sudo usermod -aG video $USER`).

**Service fails to start intermittently**: The setup script disables `getty@tty1` to prevent conflicts. If you've re-enabled it, run `sudo systemctl mask getty@tty1.service`.

**Service restart is slow**: The service is configured with a 5-second stop timeout. If it's still slow, check that the updated `setup.sh` has been run and `sudo systemctl daemon-reload` has been executed.

**MQTT not connecting**: Verify the broker address in config. Test with `mosquitto_pub -h YOUR_BROKER -t test -m hello`.

**Brightness not working**: Check that a backlight device exists: `ls /sys/class/backlight/`. The script needs sudo access to write to the brightness file. Verify with `echo 128 | sudo tee /sys/class/backlight/*/brightness`.

**Brightness resets to max after screen on**: Make sure you're running the latest `kiosk_controller.py` which tracks brightness before screen-off separately.

**Rotation not working**: Make sure `xrandr` is available. For touchscreen input mapping after rotation, install `xinput` (`sudo apt install xinput`).

**Touch input doesn't match after rotation**: Run `export DISPLAY=:0 && xinput list` to check if your touch device is detected. The script looks for common touch device names. Check `journalctl -u kiosk` to see if rotation was applied.

**HA switch doesn't update after toggling**: Make sure you're running the latest `kiosk_controller.py` which publishes status after every command.

**HA uptime sensor logs too many state changes**: Make sure you're using the latest custom component which uses a "Last boot" timestamp sensor instead of a string-based uptime.

**Chromium crashes on low-memory Pis**: Add a swap file or use `--disable-gpu` flag. You can add extra Chromium flags by editing `/opt/kiosk/kiosk_controller.py`.
