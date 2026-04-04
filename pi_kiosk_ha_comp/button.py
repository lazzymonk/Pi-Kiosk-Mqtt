"""Button platform for Pi Kiosk - refresh and reboot."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN, TOPIC_REFRESH, TOPIC_REBOOT, TOPIC_STATUS
from .coordinator import PiKioskCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the buttons."""
    coordinator: PiKioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PiKioskRefreshButton(coordinator),
        PiKioskRebootButton(coordinator),
        PiKioskRequestStatusButton(coordinator),
    ])


class PiKioskRefreshButton(ButtonEntity):
    """Button to refresh the kiosk browser."""

    _attr_has_entity_name = True
    _attr_name = "Refresh browser"
    _attr_icon = "mdi:refresh"

    def __init__(self, coordinator: PiKioskCoordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.topic_prefix}_refresh"
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

    async def async_press(self) -> None:
        await self.coordinator.async_send_command(TOPIC_REFRESH, "go")


class PiKioskRebootButton(ButtonEntity):
    """Button to reboot the Pi."""

    _attr_has_entity_name = True
    _attr_name = "Reboot"
    _attr_icon = "mdi:restart"
    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: PiKioskCoordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.topic_prefix}_reboot"
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

    async def async_press(self) -> None:
        await self.coordinator.async_send_command(TOPIC_REBOOT, "go")


class PiKioskRequestStatusButton(ButtonEntity):
    """Button to request a status update."""

    _attr_has_entity_name = True
    _attr_name = "Request status"
    _attr_icon = "mdi:update"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PiKioskCoordinator):
        self.coordinator = coordinator
        self._attr_unique_id = f"{coordinator.topic_prefix}_request_status"
        self._attr_device_info = coordinator.device_info

    @property
    def available(self) -> bool:
        return True  # Always available so you can request status even if offline

    async def async_press(self) -> None:
        await self.coordinator.async_send_command(TOPIC_STATUS, "?")
