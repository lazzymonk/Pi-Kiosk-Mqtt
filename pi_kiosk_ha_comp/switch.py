"""Switch platform for Pi Kiosk - screen on/off."""
from __future__ import annotations

from homeassistant.components.switch import SwitchEntity, SwitchDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, TOPIC_SCREEN
from .coordinator import PiKioskCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the switch."""
    coordinator: PiKioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PiKioskScreenSwitch(coordinator)])


class PiKioskScreenSwitch(SwitchEntity):
    """Switch to control the kiosk screen."""

    _attr_has_entity_name = True
    _attr_name = "Screen"
    _attr_icon = "mdi:monitor"

    def __init__(self, coordinator: PiKioskCoordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.topic_prefix}_screen"
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
    def is_on(self) -> bool:
        return self.coordinator.screen == "on"

    async def async_turn_on(self, **kwargs):
        await self.coordinator.async_send_command(TOPIC_SCREEN, "on")

    async def async_turn_off(self, **kwargs):
        await self.coordinator.async_send_command(TOPIC_SCREEN, "off")
