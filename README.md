# Raspberry Pi Kiosk Controller

Turn a headless Raspberry Pi (Lite OS) into a fullscreen web kiosk, controllable via MQTT.

## What it does

- Boots straight into a fullscreen webpage (no desktop environment needed)
- Accepts MQTT commands to **refresh**, **turn screen on/off**, **change URL**, and **reboot**
- Publishes status back via MQTT
- Auto-restarts on crash

## Requirements

- Raspberry Pi (any model with HDMI)
- Raspberry Pi OS **Lite** (Bookworm or later)
- A display connected via HDMI
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
    "screen_timeout": 0
}
```

You can also use environment variables (they override the config file):

| Env Variable | Maps to |
|---|---|
| `KIOSK_MQTT_BROKER` | `mqtt_broker` |
| `KIOSK_MQTT_PORT` | `mqtt_port` |
| `KIOSK_WEBPAGE_URL` | `webpage_url` |
| ... | (prefix any key with `KIOSK_`) |

## MQTT Topics

All topics use the prefix from config (default: `kiosk`).

| Topic | Payload | Action |
|---|---|---|
| `kiosk/refresh` | anything | Refresh the current page |
| `kiosk/screen` | `on` / `off` | Turn display on or off |
| `kiosk/screen` | anything else | Toggle display |
| `kiosk/url` | a URL string | Navigate to new URL |
| `kiosk/status` | anything | Request status report |
| `kiosk/reboot` | anything | Reboot the Pi |

Status is published to `kiosk/status/response` as retained JSON:

```json
{"online": true, "screen": "on", "url": "https://your-dashboard.com"}
```

## Testing with mosquitto

```bash
# Refresh the page
mosquitto_pub -h localhost -t kiosk/refresh -m go

# Turn screen off
mosquitto_pub -h localhost -t kiosk/screen -m off

# Turn screen on
mosquitto_pub -h localhost -t kiosk/screen -m on

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

**MQTT not connecting**: Verify the broker address in config. Test with `mosquitto_pub -h YOUR_BROKER -t test -m hello`.

**Screen on/off not working**: On Pi OS Bookworm with Wayland, you may need to install `wlopm` (`sudo apt install wlopm`). On X11, `xset` is used automatically.

**Chromium crashes on low-memory Pis**: Add a swap file or use `--disable-gpu` flag. You can add extra Chromium flags by editing `/opt/kiosk/kiosk_controller.py`.
