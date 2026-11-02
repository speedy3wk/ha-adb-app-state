"""Use an isolated Home Assistant runtime; never contact a real TV."""

from unittest.mock import AsyncMock

import pytest_asyncio
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import frame

from custom_components.adb_app_state.const import DOMAIN


@pytest_asyncio.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    frame.async_setup(instance)
    instance.config_entries = config_entries.ConfigEntries(instance, {})
    await instance.config_entries.async_initialize()
    dr.async_setup(instance)
    await dr.async_load(instance)
    yield instance
    await instance.async_stop(force=True)


@pytest_asyncio.fixture
async def entry(hass):
    config = config_entries.ConfigEntry(
        domain=DOMAIN,
        data={"host": "127.0.0.1", "port": 5555, "name": "Test TV"},
        title="Test TV",
        version=1,
        minor_version=1,
        unique_id="127.0.0.1:5555",
        source="user",
        options={},
        discovery_keys={},
        subentries_data=[],
        state=config_entries.ConfigEntryState.SETUP_IN_PROGRESS,
    )
    hass.config_entries._entries[config.entry_id] = config
    yield config
    await config._async_process_on_unload(hass)


@pytest_asyncio.fixture
async def coordinator(hass, entry):
    from custom_components.adb_app_state.coordinator import AdbAppStateCoordinator

    instance = AdbAppStateCoordinator(hass, entry)
    instance.async_request_refresh = AsyncMock()
    yield instance
    await instance.async_shutdown()
