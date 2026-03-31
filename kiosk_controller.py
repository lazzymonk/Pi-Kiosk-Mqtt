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
            if key in ("mqtt_port", "screen_timeout"):
                env_val = int(env_val)
            elif key in ("scale_factor",):
                env_val = float(env_val)
            config[key] = env_val

    return config


# ---------------------------------------------------------------------------
# Display control (uses wlr-randr for Wayland / wlopm, or xrandr / xset for X)
# ---------------------------------------------------------------------------
class DisplayController:
    """Handles turning the display on and off."""

    def __init__(self):
        self.screen_on = True
        self._detect_backend()

    def _detect_backend(self):
        """Figure out whether we're running on Wayland or X11."""
        session = os.environ.get("XDG_SESSION_TYPE", "")
        if session == "wayland" or os.environ.get("WAYLAND_DISPLAY"):
            self.backend = "wayland"
        else:
            self.backend = "x11"
        log.info("Display backend: %s", self.backend)

    def screen_off(self):
        if not self.screen_on:
            return
        try:
            if self.backend == "wayland":
                # Try wlopm first, fall back to wlr-randr
                try:
                    subprocess.run(["wlopm", "--off", "*"], check=True, timeout=5)
                except FileNotFoundError:
                    subprocess.run(
                        ["wlr-randr", "--output", self._get_output(), "--off"],
                        check=True,
                        timeout=5,
                    )
            else:
                subprocess.run(["xset", "dpms", "force", "off"], check=True, timeout=5)
            self.screen_on = False
            log.info("Screen turned OFF")
        except Exception as e:
            log.error("Failed to turn screen off: %s", e)

    def screen_turn_on(self):
        if self.screen_on:
            return
        try:
            if self.backend == "wayland":
                try:
                    subprocess.run(["wlopm", "--on", "*"], check=True, timeout=5)
                except FileNotFoundError:
                    subprocess.run(
                        ["wlr-randr", "--output", self._get_output(), "--on"],
                        check=True,
                        timeout=5,
                    )
            else:
                subprocess.run(["xset", "dpms", "force", "on"], check=True, timeout=5)
            self.screen_on = True
            log.info("Screen turned ON")
        except Exception as e:
            log.error("Failed to turn screen on: %s", e)

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
        return "HDMI-A-1"  # sensible default for Pi


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
        topics = ["refresh", "screen", "url", "status", "reboot"]
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
            "url": self.browser.url,
            "system": system,
        })
        self.client.publish(f"{self.prefix}/status/response", status, retain=True)

    def disconnect(self):
        self.client.publish(f"{self.prefix}/status/response", "offline", retain=True)
        self.client.disconnect()
        self.client.loop_stop()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    config = load_config()

    display = DisplayController()
    browser = BrowserController(config["webpage_url"], config["scale_factor"])

    # Disable screen blanking
    if display.backend == "x11":
        subprocess.run(["xset", "s", "off"], check=False)
        subprocess.run(["xset", "-dpms"], check=False)
        subprocess.run(["xset", "s", "noblank"], check=False)

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
