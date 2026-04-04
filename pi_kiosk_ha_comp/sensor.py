"""Sensor platform for Pi Kiosk - system monitoring."""
from __future__ import annotations

from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfInformation,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.entity import EntityCategory

from .const import DOMAIN
from .coordinator import PiKioskCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensors."""
    coordinator: PiKioskCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        PiKioskCPUUsageSensor(coordinator),
        PiKioskCPUTempSensor(coordinator),
        PiKioskRAMUsageSensor(coordinator),
        PiKioskRAMUsedSensor(coordinator),
        PiKioskDiskUsageSensor(coordinator),
        PiKioskDiskFreeSensor(coordinator),
        PiKioskUptimeSensor(coordinator),
        PiKioskOnlineSensor(coordinator),
    ])


class PiKioskBaseSensor(SensorEntity):
    """Base class for Pi Kiosk sensors."""

    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: PiKioskCoordinator):
        self.coordinator = coordinator
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


class PiKioskCPUUsageSensor(PiKioskBaseSensor):
    """CPU usage percentage."""

    _attr_name = "CPU usage"
    _attr_icon = "mdi:cpu-64-bit"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.topic_prefix}_cpu_usage"

    @property
    def native_value(self):
        return self.coordinator.cpu_percent


class PiKioskCPUTempSensor(PiKioskBaseSensor):
    """CPU temperature."""

    _attr_name = "CPU temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.topic_prefix}_cpu_temp"

    @property
    def native_value(self):
        return self.coordinator.cpu_temp


class PiKioskRAMUsageSensor(PiKioskBaseSensor):
    """RAM usage percentage."""

    _attr_name = "RAM usage"
    _attr_icon = "mdi:memory"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.topic_prefix}_ram_usage"

    @property
    def native_value(self):
        return self.coordinator.ram_percent


class PiKioskRAMUsedSensor(PiKioskBaseSensor):
    """RAM used in MB."""

    _attr_name = "RAM used"
    _attr_icon = "mdi:memory"
    _attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.topic_prefix}_ram_used"

    @property
    def native_value(self):
        return self.coordinator.ram_used


class PiKioskDiskUsageSensor(PiKioskBaseSensor):
    """Disk usage percentage."""

    _attr_name = "Disk usage"
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.topic_prefix}_disk_usage"

    @property
    def native_value(self):
        return self.coordinator.disk_percent


class PiKioskDiskFreeSensor(PiKioskBaseSensor):
    """Disk free space in GB."""

    _attr_name = "Disk free"
    _attr_icon = "mdi:harddisk"
    _attr_native_unit_of_measurement = UnitOfInformation.GIGABYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.topic_prefix}_disk_free"

    @property
    def native_value(self):
        return self.coordinator.disk_free


class PiKioskUptimeSensor(PiKioskBaseSensor):
    """Last boot time as a timestamp - only changes on reboot."""

    _attr_name = "Last boot"
    _attr_icon = "mdi:clock-outline"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.topic_prefix}_last_boot"

    @property
    def native_value(self) -> datetime | None:
        return self.coordinator.boot_time


class PiKioskOnlineSensor(PiKioskBaseSensor):
    """Online status - always available so you can see when it goes offline."""

    _attr_name = "Status"
    _attr_icon = "mdi:lan-connect"

    def __init__(self, coordinator):
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.topic_prefix}_online"

    @property
    def available(self) -> bool:
        return True  # Always available so we can show offline state

    @property
    def native_value(self):
        return "Online" if self.coordinator.online else "Offline"

    @property
    def icon(self):
        return "mdi:lan-connect" if self.coordinator.online else "mdi:lan-disconnect"