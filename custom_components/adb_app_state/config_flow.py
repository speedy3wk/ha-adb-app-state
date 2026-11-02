from __future__ import annotations

import logging
from typing import Any

import probatio as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, callback

from .adb_client import AdbAppStateClient, ADBAuthError, ADBConnectionError
from .const import CONF_HOST, CONF_NAME, CONF_PORT, DEFAULT_PORT, DOMAIN

_LOGGER = logging.getLogger(__name__)


class AdbAppStateConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return AdbAppStateOptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input: dict[str, Any] | None = None):
        errors: dict[str, str] = {}

        if user_input is not None:
            name = user_input[CONF_NAME]
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()

            try:
                await _async_test_connection(self.hass, host, port)
            except ADBAuthError:
                errors["base"] = "auth_failed"
            except ADBConnectionError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=name, data=user_input)

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="shield"): str,
                vol.Required(CONF_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)


class AdbAppStateOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        from .const import (
            CONF_ADBKEY_PATH,
            CONF_REUSE_ANDROIDTV_KEY,
            CONF_SCAN_INTERVAL,
            DEFAULT_REUSE_ANDROIDTV_KEY,
            DEFAULT_SCAN_INTERVAL,
        )

        options = self.entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SCAN_INTERVAL,
                    default=options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
                ): vol.Coerce(int),
                vol.Optional(
                    CONF_REUSE_ANDROIDTV_KEY,
                    default=options.get(
                        CONF_REUSE_ANDROIDTV_KEY, DEFAULT_REUSE_ANDROIDTV_KEY
                    ),
                ): bool,
                vol.Optional(
                    CONF_ADBKEY_PATH,
                    default=options.get(CONF_ADBKEY_PATH, ""),
                ): str,
            }
        )

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(step_id="init", data_schema=schema)


async def _async_test_connection(hass: HomeAssistant, host: str, port: int) -> None:
    def _sync() -> None:
        client = AdbAppStateClient(
            hass=hass,
            host=host,
            port=port,
            adbkey_path=None,
            reuse_androidtv_key=True,
        )
        try:
            client.connect()
            # cheap command
            client.shell("echo ok", timeout_s=3.0)
        finally:
            client.close()

    await hass.async_add_executor_job(_sync)
