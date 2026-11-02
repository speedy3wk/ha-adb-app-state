"""Verify polling and entities against an isolated HA coordinator."""

import base64
from unittest.mock import Mock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.adb_app_state.adb_client import ADBAuthError, ADBConnectionError
from custom_components.adb_app_state.apps.playback import async_refresh_state
from custom_components.adb_app_state.binary_sensor import InputRequiredBinarySensor
from custom_components.adb_app_state.const import (
    UI_STATE_CHOOSE_PROFILE,
    UI_STATE_IN_APP,
    UI_STATE_MOVIE,
    UI_STATE_NOT_SUPPORTED,
    UI_STATE_OFF,
)
from custom_components.adb_app_state.coordinator import (
    AppStateData,
    _parse_top_activity,
)
from custom_components.adb_app_state.sensor import UiStateSensor

from .test_detection import make_views, prime_dump


@pytest.mark.parametrize(
    "text",
    [
        "mResumedActivity: ActivityRecord{42 u0 org.example.app/.MainActivity t1}",
        "mFocusedActivity: ActivityRecord{42 u0 org.example.app/.MainActivity t1}",
    ],
)
def test_activity_parser(text):
    assert _parse_top_activity(text) == ("org.example.app", ".MainActivity")
    assert _parse_top_activity("redacted") == (None, None)


async def test_poll_disney(coordinator):
    client = Mock()
    client.shell.side_effect = [
        "mResumedActivity: ActivityRecord{42 u0 com.disney.disneyplus/.MainActivity t1}",
        base64.b64encode(make_views(b"profilesRoot")).decode(),
    ]
    with patch.object(coordinator, "_client", client):
        data = await coordinator._async_update_data()
    assert data.ui_state == UI_STATE_CHOOSE_PROFILE
    assert data.input_required is True
    assert data.debug["foreground_app"] == "com.disney.disneyplus"
    client.close.assert_called_once()


async def test_poll_prime(coordinator):
    client = Mock()
    client.shell.side_effect = [
        "mResumedActivity: ActivityRecord{42 u0 com.amazon.amazonvideo.livingroom/.Main t1}",
        prime_dump(hints="hasProtectedContent=true"),
    ]
    with patch.object(coordinator, "_client", client):
        assert (await coordinator._async_update_data()).ui_state == UI_STATE_MOVIE
    client.close.assert_called_once()


async def test_poll_unsupported_avoids_expensive_dumps(coordinator):
    client = Mock()
    client.shell.return_value = (
        "mResumedActivity: ActivityRecord{42 u0 org.example.app/.Main t1}"
    )
    with patch.object(coordinator, "_client", client):
        assert (
            await coordinator._async_update_data()
        ).ui_state == UI_STATE_NOT_SUPPORTED
    client.shell.assert_called_once_with("dumpsys activity activities", timeout_s=6.0)
    client.close.assert_called_once()


async def test_connection_failure_is_off(coordinator):
    with patch.object(
        coordinator, "_poll_sync", side_effect=ADBConnectionError("offline")
    ):
        data = await coordinator._async_update_data()
    assert data.ui_state == UI_STATE_OFF
    assert data.input_required is False
    assert data.debug["error"] == "offline"


async def test_auth_failure_is_update_failure(coordinator):
    with patch.object(coordinator, "_poll_sync", side_effect=ADBAuthError("authorize")):
        with pytest.raises(UpdateFailed, match="authorize"):
            await coordinator._async_update_data()


async def test_shell_closes_on_failure(coordinator):
    client = Mock()
    client.shell.side_effect = ADBConnectionError("timeout")
    with patch.object(coordinator, "_client", client):
        with pytest.raises(ADBConnectionError, match="timeout"):
            await coordinator.async_shell("echo ok")
    client.close.assert_called_once()


@pytest.mark.parametrize("operation", ["shell", "poll"])
async def test_failed_connect_is_closed_and_lock_is_released(coordinator, operation):
    client = Mock()
    client.connect.side_effect = ADBConnectionError("offline")
    with patch.object(coordinator, "_client", client):
        if operation == "shell":
            with pytest.raises(ADBConnectionError, match="offline"):
                await coordinator.async_shell("echo ok")
        else:
            assert (await coordinator._async_update_data()).ui_state == UI_STATE_OFF
        client.close.assert_called_once()
        client.connect.side_effect = None
        client.shell.return_value = "ok"
        assert await coordinator.async_shell("echo ok") == "ok"
    assert client.close.call_count == 2


async def test_failed_real_refresh_does_not_reuse_previous_movie(coordinator):
    coordinator.async_set_updated_data(
        AppStateData(UI_STATE_MOVIE, False, {"foreground_app": "com.disney.disneyplus"})
    )
    with patch.object(
        coordinator, "_poll_sync", side_effect=ADBAuthError("authorization lost")
    ):
        with pytest.raises(RuntimeError, match="Unable to refresh"):
            await async_refresh_state(coordinator)
    assert coordinator.last_update_success is False


async def test_entities_follow_coordinator(coordinator, entry):
    sensor = UiStateSensor(coordinator, entry)
    binary = InputRequiredBinarySensor(coordinator, entry)
    assert sensor.native_value is None
    assert binary.is_on is False
    coordinator.async_set_updated_data(
        AppStateData(
            UI_STATE_CHOOSE_PROFILE,
            True,
            {"foreground_app": "com.disney.disneyplus"},
        )
    )
    assert sensor.native_value == UI_STATE_CHOOSE_PROFILE
    assert sensor.extra_state_attributes == {
        "input_required": True,
        "foreground_app": "com.disney.disneyplus",
    }
    assert binary.is_on is True
    coordinator.async_set_updated_data(AppStateData(UI_STATE_IN_APP, False, {}))
    assert binary.is_on is False
