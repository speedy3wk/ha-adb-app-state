"""Configuration and options forms must work with the supported HA runtime."""

from unittest.mock import patch

import pytest

from custom_components.adb_app_state.adb_client import ADBAuthError, ADBConnectionError
from custom_components.adb_app_state.config_flow import (
    AdbAppStateConfigFlow,
    AdbAppStateOptionsFlowHandler,
)


async def test_config_form(hass):
    flow = AdbAppStateConfigFlow()
    flow.hass = hass
    result = await flow.async_step_user()
    assert result["type"] == "form"
    assert result["data_schema"]({"host": "127.0.0.1"}) == {
        "name": "shield",
        "host": "127.0.0.1",
        "port": 5555,
    }


async def test_config_success(hass):
    flow = AdbAppStateConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    data = {"name": "TV", "host": "127.0.0.2", "port": 5555}
    with patch(
        "custom_components.adb_app_state.config_flow._async_test_connection"
    ) as connect:
        result = await flow.async_step_user(data)
    assert result["type"] == "create_entry"
    assert result["title"] == "TV"
    assert result["data"] == data
    connect.assert_awaited_once_with(hass, "127.0.0.2", 5555)


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ADBConnectionError("offline"), "cannot_connect"),
        (ADBAuthError("authorize"), "auth_failed"),
    ],
)
async def test_config_connection_errors(hass, error, expected):
    flow = AdbAppStateConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    with patch(
        "custom_components.adb_app_state.config_flow._async_test_connection",
        side_effect=error,
    ):
        result = await flow.async_step_user(
            {"name": "TV", "host": "127.0.0.2", "port": 5555}
        )
    assert result["type"] == "form"
    assert result["errors"] == {"base": expected}


async def test_options_form_and_save(hass, entry):
    flow = AdbAppStateOptionsFlowHandler(entry)
    flow.hass = hass
    result = await flow.async_step_init()
    assert result["type"] == "form"
    assert result["data_schema"]({}) == {
        "scan_interval": 5,
        "reuse_androidtv_key": True,
        "adbkey_path": "",
    }
    options = {
        "scan_interval": 10,
        "reuse_androidtv_key": False,
        "adbkey_path": "test-key",
    }
    result = await flow.async_step_init(options)
    assert result["type"] == "create_entry"
    assert result["data"] == options
