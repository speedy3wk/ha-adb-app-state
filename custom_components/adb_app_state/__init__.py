from __future__ import annotations

import asyncio

import probatio as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .apps import disney_plus, prime_video
from .const import DOMAIN, PLATFORMS
from .coordinator import AdbAppStateCoordinator
from .validation import (
    DELAY_MS,
    PROFILE_INDEX,
    REPEAT_COUNT,
    TIMEOUT,
    disney_video,
    pin,
)
from .validation import (
    prime_video as validate_prime_video,
)

SERVICE_PREPARE_DISNEY_MOVIE = "prepare_disney_movie"
SERVICE_PREPARE_PRIME_MOVIE = "prepare_prime_movie"
SERVICE_MEDIA_DISPATCH = "media_dispatch"

SERVICE_SCHEMA_PREPARE_DISNEY = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("film_id"): disney_video,
        vol.Optional("profile_index"): PROFILE_INDEX,
        vol.Optional("pin"): pin,
        vol.Optional("pause_on_start", default=False): bool,
        vol.Optional("timeout", default=90): TIMEOUT,
    }
)


SERVICE_SCHEMA_PREPARE_PRIME = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("film_asin"): validate_prime_video,
        vol.Optional("auto_login", default=True): bool,
        vol.Optional("pause_on_start", default=False): bool,
        vol.Optional("timeout", default=90): TIMEOUT,
    }
)


SERVICE_SCHEMA_MEDIA_DISPATCH = vol.Schema(
    {
        vol.Optional("entry_id"): str,
        vol.Required("key"): str,
        vol.Optional("times", default=1): REPEAT_COUNT,
        vol.Optional("delay_ms", default=250): DELAY_MS,
    }
)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    coordinator = AdbAppStateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register services once per HA instance.
    if not hass.data[DOMAIN].get("_services_registered"):
        hass.data[DOMAIN]["_services_registered"] = True

        def _select_coordinator(entry_id: str | None) -> AdbAppStateCoordinator:
            if entry_id:
                coord = hass.data[DOMAIN].get(entry_id)
                if coord is None:
                    raise ValueError(f"Unknown entry_id: {entry_id}")
                return coord
            coords = [
                v for k, v in hass.data[DOMAIN].items() if k != "_services_registered"
            ]
            if len(coords) != 1:
                raise ValueError("Multiple entries: provide entry_id")
            return coords[0]

        async def _handle_prepare_disney(call) -> None:
            data = call.data
            coord = _select_coordinator(data.get("entry_id"))

            async with coord.action_lock:
                await disney_plus.prepare_movie(
                    coordinator=coord,
                    film_id=data["film_id"],
                    profile_index=data.get("profile_index"),
                    pin=data.get("pin"),
                    pause_on_start=data.get("pause_on_start", False),
                    timeout_s=data.get("timeout", 90),
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_PREPARE_DISNEY_MOVIE,
            _handle_prepare_disney,
            schema=SERVICE_SCHEMA_PREPARE_DISNEY,
        )

        async def _handle_prepare_prime(call) -> None:
            data = call.data
            coord = _select_coordinator(data.get("entry_id"))

            async with coord.action_lock:
                await prime_video.prepare_movie(
                    coordinator=coord,
                    film_asin=data["film_asin"],
                    auto_login=data.get("auto_login", True),
                    pause_on_start=data.get("pause_on_start", False),
                    timeout_s=data.get("timeout", 90),
                )

        hass.services.async_register(
            DOMAIN,
            SERVICE_PREPARE_PRIME_MOVIE,
            _handle_prepare_prime,
            schema=SERVICE_SCHEMA_PREPARE_PRIME,
        )

        async def _handle_media_dispatch(call) -> None:
            data = call.data
            coord = _select_coordinator(data.get("entry_id"))

            key = str(data["key"]).strip().lower()
            key_alias = {
                "fastforward": "fast-forward",
                "fast_forward": "fast-forward",
                "ff": "fast-forward",
                "rew": "rewind",
                "rw": "rewind",
                "playpause": "play-pause",
                "play_pause": "play-pause",
            }
            key = key_alias.get(key, key)

            allowed = {
                "play",
                "pause",
                "play-pause",
                "stop",
                "next",
                "previous",
                "headsethook",
                "mute",
            }
            if key not in allowed:
                raise ValueError(
                    f"Unsupported key: {key}. Note: fast-forward/rewind are intentionally disabled because they can destroy the Disney media session on this device."
                )

            times = data.get("times", 1)
            delay_s = data.get("delay_ms", 250) / 1000.0

            async with coord.action_lock:
                for i in range(times):
                    await coord.async_shell(
                        f"cmd media_session dispatch {key}", timeout_s=6.0
                    )
                    if delay_s and i != times - 1:
                        await asyncio.sleep(delay_s)

        hass.services.async_register(
            DOMAIN,
            SERVICE_MEDIA_DISPATCH,
            _handle_media_dispatch,
            schema=SERVICE_SCHEMA_MEDIA_DISPATCH,
        )

    # Ensure we have a device in the registry (nice for entity grouping).
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.title,
        manufacturer="ADB",
        model="Android TV",
    )

    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
