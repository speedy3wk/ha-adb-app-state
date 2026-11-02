from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AdbAppStateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    coordinator: AdbAppStateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([InputRequiredBinarySensor(coordinator, entry)])


class InputRequiredBinarySensor(
    CoordinatorEntity[AdbAppStateCoordinator], BinarySensorEntity
):
    _attr_has_entity_name = True

    def __init__(self, coordinator: AdbAppStateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}:{entry.entry_id}:input_required"
        self._attr_name = "Input required"
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}

    @property
    def is_on(self) -> bool:
        return bool(self.coordinator.data and self.coordinator.data.input_required)

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return None
        return {
            "ui_state": self.coordinator.data.ui_state,
            "foreground_app": (self.coordinator.data.debug or {}).get("foreground_app"),
        }
