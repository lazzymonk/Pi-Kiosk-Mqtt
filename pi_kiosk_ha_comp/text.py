"""Text platform for Pi Kiosk - URL control."""
from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TOPIC_URL
from .coordinator import PiKioskCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the text entity."""
    coordinator: PiKioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PiKioskURL(coordinator)])


class PiKioskURL(TextEntity):
    """Text entity to control the kiosk URL."""

    _attr_has_entity_name = True
    _attr_name = "URL"
    _attr_icon = "mdi:web"
    _attr_native_max = 2048
    _attr_mode = "text"

    def __init__(self, coordinator: PiKioskCoordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.topic_prefix}_url"
        self._attr_device_info = coordinator.device_info
        self._remove_listener = None

    async def async_added_to_hass(self):
        self._remove_listener = self.coordinator.add_listener(
            self._handle_coordinator_update
        )

    async def async_will_remove_from_hass(self):
        if self._remove_listener:
            self._remove_listener()

    @callback
    def _handle_coordinator_update(self):
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.coordinator.available

    @property
    def native_value(self) -> str:
        return self.coordinator.url

    async def async_set_value(self, value: str) -> None:
        await self.coordinator.async_send_command(TOPIC_URL, value)
