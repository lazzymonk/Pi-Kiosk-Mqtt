"""Number platform for Pi Kiosk - brightness control."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, TOPIC_BRIGHTNESS
from .coordinator import PiKioskCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the number entity."""
    coordinator: PiKioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PiKioskBrightness(coordinator)])


class PiKioskBrightness(NumberEntity):
    """Number entity to control kiosk backlight brightness."""

    _attr_has_entity_name = True
    _attr_name = "Brightness"
    _attr_icon = "mdi:brightness-6"
    _attr_native_min_value = 0
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator: PiKioskCoordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.topic_prefix}_brightness"
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
    def native_value(self) -> float:
        return self.coordinator.brightness

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_send_command(TOPIC_BRIGHTNESS, str(int(value)))
