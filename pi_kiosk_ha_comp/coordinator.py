"""Coordinator for Pi Kiosk - manages MQTT state."""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.components import mqtt
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_TOPIC_PREFIX,
    TOPIC_STATUS_RESPONSE,
)

_LOGGER = logging.getLogger(__name__)


class PiKioskCoordinator:
    """Manage MQTT communication for a Pi Kiosk device."""

    def __init__(self, hass: HomeAssistant, entry_id: str, name: str, topic_prefix: str):
        self.hass = hass
        self.entry_id = entry_id
        self.name = name
        self.topic_prefix = topic_prefix
        self._listeners: list[callback] = []
        self._unsubscribe = None

        # State
        self.online: bool = False
        self.screen: str = "unknown"
        self.brightness: int = 255
        self.url: str = ""
        self.cpu_percent: float | None = None
        self.cpu_temp: float | None = None
        self.ram_total: float | None = None
        self.ram_used: float | None = None
        self.ram_percent: float | None = None
        self.disk_total: float | None = None
        self.disk_used: float | None = None
        self.disk_free: float | None = None
        self.disk_percent: float | None = None
        self.boot_time: datetime | None = None

    @property
    def device_info(self) -> DeviceInfo:
        """Return device info for this kiosk."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.topic_prefix)},
            name=self.name,
            manufacturer="Raspberry Pi",
            model="Pi Kiosk",
            sw_version="1.0.0",
        )

    @property
    def available(self) -> bool:
        return self.online

    def _topic(self, suffix: str) -> str:
        return f"{self.topic_prefix}/{suffix}"

    async def async_setup(self):
        """Subscribe to the status topic."""
        self._unsubscribe = await mqtt.async_subscribe(
            self.hass,
            self._topic(TOPIC_STATUS_RESPONSE),
            self._handle_status_message,
            qos=0,
        )

    async def async_teardown(self):
        """Unsubscribe from MQTT."""
        if self._unsubscribe:
            self._unsubscribe()
            self._unsubscribe = None

    @callback
    def _handle_status_message(self, msg):
        """Handle incoming status message."""
        payload = msg.payload

        if payload == "offline":
            self.online = False
            self._notify_listeners()
            return

        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, TypeError):
            _LOGGER.warning("Invalid status payload: %s", payload)
            return

        self.online = data.get("online", False)
        self.screen = data.get("screen", "unknown")
        self.brightness = data.get("brightness", 255)
        self.url = data.get("url", "")

        system = data.get("system", {})
        self.cpu_percent = system.get("cpu_percent")
        self.cpu_temp = system.get("cpu_temp_c")
        self.ram_total = system.get("ram_total_mb")
        self.ram_used = system.get("ram_used_mb")
        self.ram_percent = system.get("ram_percent")
        self.disk_total = system.get("disk_total_gb")
        self.disk_used = system.get("disk_used_gb")
        self.disk_free = system.get("disk_free_gb")
        self.disk_percent = system.get("disk_percent")

        # Convert uptime string (e.g. "2h 34m 12s") to a boot timestamp
        uptime_str = system.get("uptime")
        if uptime_str:
            try:
                hours = minutes = seconds = 0
                parts = re.findall(r"(\d+)([hms])", uptime_str)
                for val, unit in parts:
                    if unit == "h":
                        hours = int(val)
                    elif unit == "m":
                        minutes = int(val)
                    elif unit == "s":
                        seconds = int(val)
                uptime_seconds = hours * 3600 + minutes * 60 + seconds
                self.boot_time = datetime.now(timezone.utc) - timedelta(seconds=uptime_seconds)
            except Exception:
                pass

        self._notify_listeners()

    @callback
    def add_listener(self, update_callback):
        """Register a listener for state updates."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener():
            self._listeners.remove(update_callback)

        return remove_listener

    @callback
    def _notify_listeners(self):
        """Notify all registered listeners."""
        for listener in self._listeners:
            listener()

    async def async_send_command(self, topic_suffix: str, payload: str):
        """Publish an MQTT command."""
        await mqtt.async_publish(
            self.hass,
            self._topic(topic_suffix),
            payload,
        )
