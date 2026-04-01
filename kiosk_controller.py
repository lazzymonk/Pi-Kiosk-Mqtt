#!/usr/bin/env python3
"""
Raspberry Pi Kiosk Controller
Boots into a fullscreen webpage and accepts MQTT commands to:
  - Refresh the browser
  - Turn the display on/off
  - Change the URL

MQTT Topics:
  kiosk/refresh      -> any payload triggers a page refresh
  kiosk/screen       -> "on" or "off"
  kiosk/url          -> new URL to navigate to
  kiosk/status       -> any payload triggers a status report
  kiosk/reboot       -> reboots the Pi

Status is published to: kiosk/status/response
"""

import subprocess
import signal
import sys
import json
import time
import logging
import os
from pathlib import Path

try:
    import paho.mqtt.client as mqtt
except ImportError:
    print("ERROR: paho-mqtt not installed. Run: pip3 install paho-mqtt")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Configuration - override via /etc/kiosk/config.json or environment vars
# ---------------------------------------------------------------------------
DEFAULT_CONFIG = {
    "mqtt_broker": "localhost",
    "mqtt_port": 1883,
    "mqtt_username": "",
    "mqtt_password": "",
    "mqtt_topic_prefix": "kiosk",
    "webpage_url": "https://example.com",
    "screen_timeout": 0,  # 0 = never blank
    "scale_factor": 1.0,  # adjust if content doesn't fit (try 0.9-1.0 for small screens)
    "rotation": 0,  # 0, 90, 180, or 270 degrees
    "brightness": 255,  # default backlight brightness (0-255)
    "screen_off_method": "backlight",  # "backlight" (set to 0) or "dpms" (signal off)
}

CONFIG_FILE = Path("/etc/kiosk/config.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("kiosk")


def load_config() -> dict:
    """Load config with priority: env vars > config file > defaults."""
    config = dict(DEFAULT_CONFIG)

    # Layer 1: config file
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE) as f:
                file_config = json.load(f)
            config.update(file_config)
            log.info("Loaded config from %s", CONFIG_FILE)
        except Exception as e:
            log.warning("Could not read config file: %s", e)

    # Layer 2: environment variables (KIOSK_MQTT_BROKER, KIOSK_WEBPAGE_URL, etc.)
    for key in DEFAULT_CONFIG:
        env_key = f"KIOSK_{key.upper()}"
        env_val = os.environ.get(env_key)
        if env_val is not None:
            # Cast to int for port
            if key in ("mqtt_port", "screen_timeout", "rotation", "brightness"):
                env_val = int(env_val)
            elif key in ("scale_factor",):
                env_val = float(env_val)
            config[key] = env_val

    return config


# ---------------------------------------------------------------------------
# Display control
# ---------------------------------------------------------------------------
class DisplayController:
    """Handles turning the display on/off and backlight brightness."""

    def __init__(self, screen_off_method: str = "backlight", default_brightness: int = 255):
        self.screen_on = True
        self.screen_off_method = screen_off_method
        self.default_brightness = max(0, min(255, default_brightness))
        self.current_brightness = self.default_brightness
        self._backlight_path = self._find_backlight()
        self._detect_backend()

    def _detect_backend(self):
        """Figure out whether we're running on Wayland or X11."""
        session = os.environ.get("XDG_SESSION_TYPE", "")
        if session == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
            self.backend = "wayland"
        else:
            self.backend = "x11"
        log.info("Display backend: %s", self.backend)
        log.info("Screen off method: %s", self.screen_off_method)
        if self._backlight_path:
            log.info("Backlight device: %s", self._backlight_path)
        else:
            log.warning("No backlight device found in /sys/class/backlight/")

    def _find_backlight(self) -> str:
        """Find the first backlight device path."""
        backlight_dir = Path("/sys/class/backlight")
        if backlight_dir.exists():
            for entry in backlight_dir.iterdir():
                brightness_file = entry / "brightness"
                if brightness_file.exists():
                    return str(entry)
        return ""

    def set_brightness(self, value: int):
        """Set backlight brightness (0-255)."""
        value = max(0, min(255, value))
        if not self._backlight_path:
            log.error("No backlight device found")
            return False
        try:
            brightness_file = os.path.join(self._backlight_path, "brightness")
            subprocess.run(
                ["sudo", "tee", brightness_file],
                input=str(value).encode(),
                stdout=subprocess.DEVNULL,
                check=True, timeout=5,
            )
            self.current_brightness = value
            log.info("Backlight set to %d", value)

            # Update screen state based on brightness
            if value == 0:
                self.screen_on = False
            else:
                self.screen_on = True

            return True
        except Exception as e:
            log.error("Failed to set backlight: %s", e)
            return False

    def screen_off(self):
        if not self.screen_on:
            return
        if self.screen_off_method == "backlight":
            self.set_brightness(0)
        else:
            self._dpms_off()
            self.screen_on = False
        log.info("Screen turned OFF (method: %s)", self.screen_off_method)

    def screen_turn_on(self):
        if self.screen_on:
            return
        if self.screen_off_method == "backlight":
            # Restore to the last non-zero brightness, or default
            restore = self.default_brightness if self.current_brightness == 0 else self.current_brightness
            if restore == 0:
                restore = 255
            self.set_brightness(restore)
        else:
            self._dpms_on()
            self.screen_on = True
        log.info("Screen turned ON (method: %s)", self.screen_off_method)

    def _dpms_off(self):
        try:
            if self.backend == "wayland":
                try:
                    subprocess.run(["wlopm", "--off", "*"], check=True, timeout=5)
                except FileNotFoundError:
                    subprocess.run(
                        ["wlr-randr", "--output", self._get_output(), "--off"],
                        check=True, timeout=5,
                    )
            else:
                subprocess.run(["xset", "dpms", "force", "off"], check=True, timeout=5)
        except Exception as e:
            log.error("DPMS off failed: %s", e)

    def _dpms_on(self):
        try:
            if self.backend == "wayland":
                try:
                    subprocess.run(["wlopm", "--on", "*"], check=True, timeout=5)
                except FileNotFoundError:
                    subprocess.run(
                        ["wlr-randr", "--output", self._get_output(), "--on"],
                        check=True, timeout=5,
                    )
            else:
                subprocess.run(["xset", "dpms", "force", "on"], check=True, timeout=5)
        except Exception as e:
            log.error("DPMS on failed: %s", e)

    def _get_output(self) -> str:
        """Get the first connected output name for wlr-randr."""
        try:
            result = subprocess.run(
                ["wlr-randr"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if not line.startswith(" ") and line.strip():
                    return line.split()[0]
        except Exception:
            pass
        return "HDMI-A-1"


# ---------------------------------------------------------------------------
# Browser control
# ---------------------------------------------------------------------------
class BrowserController:
    """Manages Chromium in kiosk mode."""

    def __init__(self, url: str, scale_factor: float = 1.0):
        self.url = url
        self.scale_factor = scale_factor
        self.process = None

    def _get_screen_resolution(self):
        """Get the current screen resolution."""
        try:
            result = subprocess.run(
                ["xdpyinfo"], capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "dimensions:" in line:
                    # e.g. "  dimensions:    1920x1080 pixels ..."
                    res = line.split()[1]  # "1920x1080"
                    return res
        except Exception:
            pass
        return "1920x1080"

    def start(self):
        """Launch Chromium in kiosk mode."""
        resolution = self._get_screen_resolution()
        cmd = [
            "chromium",
            "--noerrdialogs",
            "--disable-infobars",
            "--disable-translate",
            "--disable-features=TranslateUI",
            "--disable-session-crashed-bubble",
            "--disable-component-update",
            "--kiosk",
            "--incognito",
            "--no-first-run",
            "--start-fullscreen",
            "--start-maximized",
            "--window-position=0,0",
            f"--window-size={resolution.replace('x', ',')}",
            f"--force-device-scale-factor={self.scale_factor}",
            "--high-dpi-support=1",
            "--autoplay-policy=no-user-gesture-required",
            "--check-for-update-interval=31536000",  # don't check for updates
            self.url,
        ]
        log.info("Starting Chromium: %s", self.url)
        self.process = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )

    def refresh(self):
        """Send F5 to Chromium via xdotool."""
        try:
            subprocess.run(["xdotool", "key", "F5"], check=True, timeout=5)
            log.info("Browser refreshed")
        except Exception as e:
            log.error("Failed to refresh: %s", e)

    def navigate(self, url: str):
        """Kill and restart Chromium with new URL (most reliable for kiosk)."""
        self.url = url
        self.stop()
        time.sleep(1)
        self.start()
        log.info("Navigated to: %s", url)

    def stop(self):
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None


# ---------------------------------------------------------------------------
# MQTT handler
# ---------------------------------------------------------------------------
class KioskMQTT:
    def __init__(self, config: dict, display: DisplayController, browser: BrowserController):
        self.config = config
        self.display = display
        self.browser = browser
        self.prefix = config["mqtt_topic_prefix"]

        self.client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if config["mqtt_username"]:
            self.client.username_pw_set(config["mqtt_username"], config["mqtt_password"])

        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.on_disconnect = self._on_disconnect

        self.client.will_set(f"{self.prefix}/status/response", "offline", retain=True)

    def connect(self):
        log.info("Connecting to MQTT broker %s:%s", self.config["mqtt_broker"], self.config["mqtt_port"])
        self.client.connect(self.config["mqtt_broker"], self.config["mqtt_port"], keepalive=60)
        self.client.loop_start()

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        log.info("MQTT connected (rc=%s)", rc)
        topics = ["refresh", "screen", "brightness", "url", "status", "reboot"]
        for t in topics:
            client.subscribe(f"{self.prefix}/{t}")
            log.info("  Subscribed to %s/%s", self.prefix, t)

        self._publish_status()

    def _on_disconnect(self, client, userdata, flags, rc, properties=None):
        log.warning("MQTT disconnected (rc=%s), will auto-reconnect", rc)

    def _on_message(self, client, userdata, msg):
        topic = msg.topic
        payload = msg.payload.decode("utf-8", errors="replace").strip().lower()
        log.info("MQTT message: %s -> %s", topic, payload)

        action = topic.replace(f"{self.prefix}/", "", 1)

        if action == "refresh":
            self.browser.refresh()

        elif action == "screen":
            if payload == "off":
                self.display.screen_off()
            elif payload == "on":
                self.display.screen_turn_on()
            else:
                # Toggle
                if self.display.screen_on:
                    self.display.screen_off()
                else:
                    self.display.screen_turn_on()

        elif action == "brightness":
            try:
                value = int(payload)
                self.display.set_brightness(value)
            except ValueError:
                log.warning("Invalid brightness value: %s (must be 0-255)", payload)

        elif action == "url":
            # For URL, use the raw (non-lowered) payload
            raw = msg.payload.decode("utf-8", errors="replace").strip()
            if raw:
                self.browser.navigate(raw)

        elif action == "status":
            self._publish_status()

        elif action == "reboot":
            log.info("Reboot requested via MQTT")
            self._publish_status()
            subprocess.run(["sudo", "reboot"], check=False)
    @staticmethod
    def _get_system_stats() -> dict:
        """Gather CPU, RAM, temperature, and disk stats."""
        stats = {}
 
        # CPU usage (1-second sample)
        try:
            with open("/proc/stat") as f:
                line1 = f.readline().split()
            time.sleep(0.5)
            with open("/proc/stat") as f:
                line2 = f.readline().split()
            idle1 = int(line1[4])
            idle2 = int(line2[4])
            total1 = sum(int(x) for x in line1[1:])
            total2 = sum(int(x) for x in line2[1:])
            cpu_pct = round(100.0 * (1.0 - (idle2 - idle1) / max(total2 - total1, 1)), 1)
            stats["cpu_percent"] = cpu_pct
        except Exception:
            stats["cpu_percent"] = None
 
        # CPU temperature
        try:
            with open("/sys/class/thermal/thermal_zone0/temp") as f:
                stats["cpu_temp_c"] = round(int(f.read().strip()) / 1000.0, 1)
        except Exception:
            stats["cpu_temp_c"] = None
 
        # RAM
        try:
            with open("/proc/meminfo") as f:
                meminfo = {}
                for line in f:
                    parts = line.split()
                    meminfo[parts[0].rstrip(":")] = int(parts[1])
            total = meminfo["MemTotal"]
            available = meminfo["MemAvailable"]
            used = total - available
            stats["ram_total_mb"] = round(total / 1024, 1)
            stats["ram_used_mb"] = round(used / 1024, 1)
            stats["ram_percent"] = round(100.0 * used / max(total, 1), 1)
        except Exception:
            stats["ram_total_mb"] = None
            stats["ram_used_mb"] = None
            stats["ram_percent"] = None
 
        # Disk (root filesystem)
        try:
            st = os.statvfs("/")
            total = st.f_blocks * st.f_frsize
            free = st.f_bavail * st.f_frsize
            used = total - free
            stats["disk_total_gb"] = round(total / (1024 ** 3), 1)
            stats["disk_used_gb"] = round(used / (1024 ** 3), 1)
            stats["disk_free_gb"] = round(free / (1024 ** 3), 1)
            stats["disk_percent"] = round(100.0 * used / max(total, 1), 1)
        except Exception:
            stats["disk_total_gb"] = None
            stats["disk_used_gb"] = None
            stats["disk_free_gb"] = None
            stats["disk_percent"] = None
 
        # Uptime
        try:
            with open("/proc/uptime") as f:
                uptime_secs = int(float(f.read().split()[0]))
            hours, remainder = divmod(uptime_secs, 3600)
            minutes, seconds = divmod(remainder, 60)
            stats["uptime"] = f"{hours}h {minutes}m {seconds}s"
        except Exception:
            stats["uptime"] = None
 
        return stats
    

    def _publish_status(self):
        system = self._get_system_stats()
        status = json.dumps({
            "online": True,
            "screen": "on" if self.display.screen_on else "off",
            "brightness": self.display.current_brightness,
            "url": self.browser.url,
            "system": system,
        })
        self.client.publish(f"{self.prefix}/status/response", status, retain=True)

    def disconnect(self):
        self.client.publish(f"{self.prefix}/status/response", "offline", retain=True)
        self.client.disconnect()
        self.client.loop_stop()


# ---------------------------------------------------------------------------
# Display rotation
# ---------------------------------------------------------------------------
ROTATION_MAP = {
    0: "normal",
    90: "right",
    180: "inverted",
    270: "left",
}

# Coordinate Transformation Matrix for xinput, mapping rotation to touch input
# See: https://wiki.archlinux.org/title/Calibrating_Touchscreen
TOUCH_MATRIX = {
    0:   "1 0 0 0 1 0 0 0 1",
    90:  "0 1 0 -1 0 1 0 0 1",
    180: "-1 0 1 0 -1 1 0 0 1",
    270: "0 -1 1 1 0 0 0 0 1",
}


def _find_touch_devices():
    """Find all touchscreen input device IDs via xinput."""
    devices = []
    try:
        result = subprocess.run(
            ["xinput", "list", "--name-only"],
            capture_output=True, text=True, timeout=5,
        )
        id_result = subprocess.run(
            ["xinput", "list", "--id-only"],
            capture_output=True, text=True, timeout=5,
        )
        names = result.stdout.strip().splitlines()
        ids = id_result.stdout.strip().splitlines()

        touch_keywords = ["touch", "Touch", "TOUCH", "FT5406", "Goodix", "eGalax", "HID"]
        for name, dev_id in zip(names, ids):
            if any(kw in name for kw in touch_keywords):
                devices.append((dev_id.strip(), name.strip()))
    except Exception:
        pass

    # Fallback: try to find any pointer device with touch-like properties
    if not devices:
        try:
            result = subprocess.run(
                ["xinput", "list"], capture_output=True, text=True, timeout=5,
            )
            for line in result.stdout.splitlines():
                if "slave  pointer" in line or "floating slave" in line:
                    # Extract id=N
                    for part in line.split():
                        if part.startswith("id="):
                            dev_id = part.split("=")[1]
                            # Check if it has the coordinate transform property
                            prop_result = subprocess.run(
                                ["xinput", "list-props", dev_id],
                                capture_output=True, text=True, timeout=5,
                            )
                            if "Coordinate Transformation Matrix" in prop_result.stdout:
                                dev_name = line.split("id=")[0].strip().rstrip("\t")
                                devices.append((dev_id, dev_name))
        except Exception:
            pass

    return devices


def apply_rotation(degrees: int):
    """Rotate the X display and touchscreen input using xrandr and xinput."""
    orientation = ROTATION_MAP.get(degrees)
    if orientation is None:
        log.warning("Invalid rotation %s, must be 0/90/180/270. Skipping.", degrees)
        return
    if degrees == 0:
        log.info("Rotation: 0 (normal)")
        return

    # Find the connected output name
    try:
        result = subprocess.run(
            ["xrandr", "--query"], capture_output=True, text=True, timeout=5
        )
        output_name = None
        for line in result.stdout.splitlines():
            if " connected" in line:
                output_name = line.split()[0]
                break

        if not output_name:
            log.error("Could not find connected display for rotation")
            return

        subprocess.run(
            ["xrandr", "--output", output_name, "--rotate", orientation],
            check=True,
            timeout=5,
        )
        log.info("Rotated display %s to %s (%d degrees)", output_name, orientation, degrees)
    except Exception as e:
        log.error("Failed to rotate display: %s", e)
        return

    # Apply matching coordinate transform to all touch devices
    matrix = TOUCH_MATRIX.get(degrees, TOUCH_MATRIX[0])
    touch_devices = _find_touch_devices()

    if not touch_devices:
        log.warning("No touchscreen devices found to rotate")
        return

    for dev_id, dev_name in touch_devices:
        try:
            subprocess.run(
                ["xinput", "set-prop", dev_id,
                 "Coordinate Transformation Matrix"] + matrix.split(),
                check=True, timeout=5,
            )
            log.info("Rotated touch input for '%s' (id=%s)", dev_name, dev_id)
        except Exception as e:
            log.error("Failed to rotate touch for '%s': %s", dev_name, e)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    config = load_config()

    display = DisplayController(
        screen_off_method=config["screen_off_method"],
        default_brightness=config["brightness"],
    )
    browser = BrowserController(config["webpage_url"], config["scale_factor"])

    # Disable screen blanking
    if display.backend == "x11":
        subprocess.run(["xset", "s", "off"], check=False)
        subprocess.run(["xset", "-dpms"], check=False)
        subprocess.run(["xset", "s", "noblank"], check=False)

    # Set initial brightness
    if display._backlight_path:
        display.set_brightness(config["brightness"])

    # Apply display rotation before launching browser
    apply_rotation(config["rotation"])

    browser.start()
    time.sleep(3)  # give chromium a moment to launch

    kiosk_mqtt = KioskMQTT(config, display, browser)
    kiosk_mqtt.connect()

    def shutdown(signum, frame):
        log.info("Shutting down...")
        kiosk_mqtt.disconnect()
        browser.stop()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    log.info("Kiosk controller running. Waiting for MQTT commands...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
