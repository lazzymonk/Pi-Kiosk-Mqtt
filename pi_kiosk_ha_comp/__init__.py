"""The Pi Kiosk integration."""
from __future__ import annotations

import json
import logging

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN, CONF_NAME, CONF_TOPIC_PREFIX, DEFAULT_NAME, DEFAULT_TOPIC_PREFIX
from .coordinator import PiKioskCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["switch", "number", "sensor", "button", "text"]
DISCOVERY_TOPIC = "pi_kiosk/discovery/#"


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Pi Kiosk component - subscribe to discovery topic."""
    hass.data.setdefault(DOMAIN, {})

    async def _async_discovery_handler(msg):
        """Handle a discovery message from a kiosk."""
        try:
            payload = json.loads(msg.payload)
        except (json.JSONDecodeError, TypeError):
            return

        topic_prefix = payload.get("topic_prefix")
        hostname = payload.get("hostname", "Pi Kiosk")

        if not topic_prefix:
            return

        # Check if this prefix is already configured
        existing_prefixes = set()
        for entry in hass.config_entries.async_entries(DOMAIN):
            existing_prefixes.add(entry.data.get(CONF_TOPIC_PREFIX))

        if topic_prefix in existing_prefixes:
            return

        _LOGGER.info(
            "Discovered new Pi Kiosk: %s (prefix: %s)", hostname, topic_prefix
        )

        # Trigger a config flow for this discovered kiosk
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": "mqtt"},
                data={
                    CONF_TOPIC_PREFIX: topic_prefix,
                    CONF_NAME: hostname,
                },
            )
        )

    # Subscribe to discovery topic once MQTT is ready
    if await mqtt.async_wait_for_mqtt_client(hass):
        await mqtt.async_subscribe(hass, DISCOVERY_TOPIC, _async_discovery_handler, qos=0)
        _LOGGER.info("Subscribed to Pi Kiosk discovery topic")

    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Pi Kiosk from a config entry."""
    name = entry.data.get(CONF_NAME, DEFAULT_NAME)
    topic_prefix = entry.data.get(CONF_TOPIC_PREFIX, DEFAULT_TOPIC_PREFIX)

    coordinator = PiKioskCoordinator(hass, entry.entry_id, name, topic_prefix)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        coordinator: PiKioskCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_teardown()

    return unload_ok
