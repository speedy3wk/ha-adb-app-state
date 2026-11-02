"""Run real platform setup, action dispatch and unloading with mocked ADB."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, loader
from homeassistant.helpers import entity_registry as er

from custom_components.adb_app_state import async_setup_entry, async_unload_entry
from custom_components.adb_app_state.const import DOMAIN, UI_STATE_HOME
from custom_components.adb_app_state.coordinator import (
    AdbAppStateCoordinator,
    AppStateData,
)


async def test_platform_setup_and_unload(hass, entry):
    loader.async_setup(hass)
    await er.async_load(hass)
    entry._async_set_state(hass, config_entries.ConfigEntryState.NOT_LOADED, None)
    with (
        patch.object(hass.config_entries._store, "async_delay_save"),
        patch.object(
            AdbAppStateCoordinator,
            "_poll_sync",
            return_value=AppStateData(
                UI_STATE_HOME, False, {"foreground_app": "com.disney.disneyplus"}
            ),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        entities = er.async_entries_for_config_entry(er.async_get(hass), entry.entry_id)
        assert len(entities) == 2
        ui_entity = next(item for item in entities if item.domain == "sensor")
        input_entity = next(item for item in entities if item.domain == "binary_sensor")
        assert hass.states.get(ui_entity.entity_id).state == UI_STATE_HOME
        assert hass.states.get(input_entity.entity_id).state == "off"
        assert hass.services.has_service(DOMAIN, "prepare_disney_movie")
        assert hass.services.has_service(DOMAIN, "prepare_prime_movie")
        assert hass.services.has_service(DOMAIN, "media_dispatch")
        assert await hass.config_entries.async_unload(entry.entry_id)
        assert entry.entry_id not in hass.data[DOMAIN]


@pytest.fixture
async def services(hass, entry):
    with (
        patch.object(
            AdbAppStateCoordinator,
            "async_config_entry_first_refresh",
            new_callable=AsyncMock,
        ),
        patch.object(hass.config_entries, "async_forward_entry_setups"),
        patch.object(hass.config_entries, "async_unload_platforms", return_value=True),
    ):
        assert await async_setup_entry(hass, entry)
        yield hass.data[DOMAIN][entry.entry_id]
        assert await async_unload_entry(hass, entry)


async def test_media_dispatch(hass, services):
    with patch.object(services, "async_shell") as shell:
        await hass.services.async_call(
            DOMAIN,
            "media_dispatch",
            {"key": "play_pause", "times": 2, "delay_ms": 0},
            blocking=True,
        )
    assert shell.await_count == 2
    shell.assert_awaited_with("cmd media_session dispatch play-pause", timeout_s=6.0)


async def test_media_dispatch_rejects_seek(hass, services):
    with patch.object(services, "async_shell") as shell:
        with pytest.raises(ValueError, match="intentionally disabled"):
            await hass.services.async_call(
                DOMAIN, "media_dispatch", {"key": "rewind"}, blocking=True
            )
    shell.assert_not_awaited()


@pytest.mark.parametrize(
    ("service", "module", "data"),
    [
        ("prepare_disney_movie", "disney_plus", {"film_id": "test-video"}),
        ("prepare_prime_movie", "prime_video", {"film_asin": "TESTASIN"}),
    ],
)
async def test_prepare_actions_forward_options(hass, services, service, module, data):
    with patch(
        f"custom_components.adb_app_state.apps.{module}.prepare_movie"
    ) as prepare:
        await hass.services.async_call(DOMAIN, service, data, blocking=True)
    assert prepare.await_args.kwargs["coordinator"] is services
    assert prepare.await_args.kwargs["pause_on_start"] is False
    assert prepare.await_args.kwargs["timeout_s"] == 90
    for key, value in data.items():
        assert prepare.await_args.kwargs[key] == value
