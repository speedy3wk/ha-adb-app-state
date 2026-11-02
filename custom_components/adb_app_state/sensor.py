from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import AdbAppStateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities
) -> None:
    coordinator: AdbAppStateCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            UiStateSensor(coordinator, entry),
        ]
    )


class _Base(CoordinatorEntity[AdbAppStateCoordinator], SensorEntity):
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AdbAppStateCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
        name: str,
    ):
        super().__init__(coordinator)
        self._attr_unique_id = f"{DOMAIN}:{entry.entry_id}:{unique_suffix}"
        self._attr_name = name
        self._entry_id = entry.entry_id
        self._attr_device_info = {"identifiers": {(DOMAIN, entry.entry_id)}}

    async def async_update(self) -> None:
        await self.coordinator.async_request_refresh()


class UiStateSensor(_Base):
    def __init__(self, coordinator: AdbAppStateCoordinator, entry: ConfigEntry):
        super().__init__(coordinator, entry, "ui_state", "UI state")

    @property
    def native_value(self):
        return self.coordinator.data.ui_state if self.coordinator.data else None

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return None
        return {
            "input_required": self.coordinator.data.input_required,
            "foreground_app": (self.coordinator.data.debug or {}).get("foreground_app"),
        }
