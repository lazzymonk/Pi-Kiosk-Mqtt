# Raspberry Pi Kiosk Controller

Turn a headless Raspberry Pi (Lite OS) into a fullscreen web kiosk, controllable via MQTT.

## What it does

- Boots straight into a fullscreen webpage (no desktop environment needed)
- Accepts MQTT commands to **refresh**, **turn screen on/off**, **adjust brightness**, **change URL**, and **reboot**
- Display rotation support (0, 90, 180, 270 degrees) with automatic touchscreen input mapping
- Backlight brightness control (0-255) via MQTT
- Configurable screen-off method: backlight dimming or DPMS signal
- Publishes detailed status (including CPU, RAM, temperature, disk, uptime) via MQTT
- Auto-restarts on crash

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
    "screen_off_method": "backlight"
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

- **`"backlight"`** (recommended for Pi touchscreens) - sets the backlight to 0 via `/sys/class/backlight/*/brightness`. Turning the screen back on restores the previous brightness. This is more reliable for DSI-connected displays.
- **`"dpms"`** - sends a DPMS signal to power off the display. Works better with HDMI monitors.

The `"brightness"` option sets the default backlight level on startup and is the level restored when turning the screen back on.

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

## Home Assistant Example

```yaml
# configuration.yaml
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

    - name: "Kiosk Uptime"
      state_topic: "kiosk/status/response"
      value_template: "{{ value_json.system.uptime }}"

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

## Multiple Kiosks

Run several Pis with different topic prefixes:

```json
{"mqtt_topic_prefix": "kiosk/kitchen"}
{"mqtt_topic_prefix": "kiosk/office"}
```

## Troubleshooting

**Black screen / no browser**: Check `journalctl -u kiosk -f` for errors. Make sure your user has permission to start X (`sudo usermod -aG video $USER`).

**Service fails to start intermittently**: The setup script disables `getty@tty1` to prevent conflicts. If you've re-enabled it, run `sudo systemctl mask getty@tty1.service`.

**MQTT not connecting**: Verify the broker address in config. Test with `mosquitto_pub -h YOUR_BROKER -t test -m hello`.

**Brightness not working**: Check that a backlight device exists: `ls /sys/class/backlight/`. The script needs sudo access to write to the brightness file. Verify with `echo 128 | sudo tee /sys/class/backlight/*/brightness`.

**Rotation not working**: Make sure `xrandr` is available. For touchscreen input mapping after rotation, install `xinput` (`sudo apt install xinput`).

**Touch input doesn't match after rotation**: Run `export DISPLAY=:0 && xinput list` to check if your touch device is detected. The script looks for common touch device names. Check `journalctl -u kiosk` to see if rotation was applied.

**Chromium crashes on low-memory Pis**: Add a swap file or use `--disable-gpu` flag. You can add extra Chromium flags by editing `/opt/kiosk/kiosk_controller.py`.
