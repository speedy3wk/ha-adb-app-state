from __future__ import annotations

import base64
import hashlib
import logging
import re
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .adb_client import (
    AdbAppStateClient,
    ADBAuthError,
    ADBConnectionError,
)
from .apps import detect_ui_state, prime_video
from .const import (
    CONF_ADBKEY_PATH,
    CONF_REUSE_ANDROIDTV_KEY,
    CONF_SCAN_INTERVAL,
    DEFAULT_PORT,
    DEFAULT_REUSE_ANDROIDTV_KEY,
    DEFAULT_SCAN_INTERVAL,
    UI_STATE_IN_APP,
    UI_STATE_NOT_SUPPORTED,
    UI_STATE_OFF,
)
from .view_dump import (
    parse_primary_package_from_window_views_zip,
    parse_visible_components_from_window_views_zip,
)

_LOGGER = logging.getLogger(__name__)


_DISNEY_PACKAGE = "com.disney.disneyplus"
_PRIME_PACKAGE = "com.amazon.amazonvideo.livingroom"

_RESUMED_ACTIVITY_RE = re.compile(
    r"mResumedActivity:.*?\s(?P<pkg>[a-zA-Z0-9_.]+)/(?P<activity>[^\s}]+)",
    re.IGNORECASE,
)
_FOCUSED_ACTIVITY_RE = re.compile(
    r"mFocusedActivity:.*?\s(?P<pkg>[a-zA-Z0-9_.]+)/(?P<activity>[^\s}]+)",
    re.IGNORECASE,
)


def _parse_top_activity(dumpsys_text: str) -> tuple[str | None, str | None]:
    for line in (dumpsys_text or "").splitlines():
        m = _RESUMED_ACTIVITY_RE.search(line)
        if m:
            return m.group("pkg"), m.group("activity")
    for line in (dumpsys_text or "").splitlines():
        m = _FOCUSED_ACTIVITY_RE.search(line)
        if m:
            return m.group("pkg"), m.group("activity")
    return None, None


@dataclass(frozen=True)
class AppStateData:
    ui_state: str
    input_required: bool
    debug: dict[str, Any]


class AdbAppStateCoordinator(DataUpdateCoordinator[AppStateData]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        options = entry.options

        scan_interval_s = int(options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL))
        super().__init__(
            hass,
            _LOGGER,
            name=f"adb_app_state_{entry.entry_id}",
            update_interval=timedelta(seconds=scan_interval_s),
        )

        host = entry.data["host"]
        port = int(entry.data.get("port", DEFAULT_PORT))
        adbkey_path = options.get(CONF_ADBKEY_PATH) or None
        reuse_androidtv_key = bool(
            options.get(CONF_REUSE_ANDROIDTV_KEY, DEFAULT_REUSE_ANDROIDTV_KEY)
        )

        self._client = AdbAppStateClient(
            hass=hass,
            host=host,
            port=port,
            adbkey_path=adbkey_path,
            reuse_androidtv_key=reuse_androidtv_key,
        )

    async def _async_update_data(self) -> AppStateData:
        try:
            return await self.hass.async_add_executor_job(self._poll_sync)
        except ADBAuthError as exc:
            raise UpdateFailed(str(exc)) from exc
        except ADBConnectionError as exc:
            return AppStateData(
                ui_state=UI_STATE_OFF,
                input_required=False,
                debug={"error": str(exc)},
            )
        except Exception as exc:  # noqa: BLE001
            raise UpdateFailed(f"Unexpected error: {exc}") from exc

    async def async_shell(self, command: str, *, timeout_s: float = 8.0) -> str:
        def _sync() -> str:
            self._client.connect()
            try:
                return self._client.shell(command, timeout_s=timeout_s)
            finally:
                self._client.close()

        return await self.hass.async_add_executor_job(_sync)

    def _poll_sync(self) -> AppStateData:
        debug: dict[str, Any] = {}
        self._client.connect()
        try:
            # Determine foreground app (lightweight), then only use dumps for supported apps.
            activity_dump = self._client.shell(
                "dumpsys activity activities", timeout_s=6.0
            )
            foreground_app, top_activity = _parse_top_activity(activity_dump)
            if foreground_app:
                debug["foreground_app"] = foreground_app
            if top_activity:
                debug["top_activity"] = top_activity

            if not foreground_app:
                # Fallback: derive foreground from view dump (works on some devices when activity is redacted).
                view_b64 = self._client.shell(
                    "cmd window dump-visible-window-views | base64", timeout_s=15.0
                )
                try:
                    zip_bytes = base64.b64decode(view_b64) if view_b64 else b""
                except Exception:  # noqa: BLE001
                    zip_bytes = b""
                debug["window_views_zip_len"] = len(zip_bytes)
                debug["screen_id"] = hashlib.sha1(zip_bytes).hexdigest()[:12]

                ignore_pkgs = {
                    "android",
                    "com.android.systemui",
                    "com.android.settings",
                    "com.google.android.gms",
                    "com.google.android.inputmethod.latin",
                }
                foreground_app = parse_primary_package_from_window_views_zip(
                    zip_bytes, ignore_packages=ignore_pkgs
                )
                if foreground_app:
                    debug["foreground_app"] = foreground_app

                visible_components = parse_visible_components_from_window_views_zip(
                    zip_bytes
                )
                debug["visible_components"] = visible_components

                if foreground_app == _DISNEY_PACKAGE:
                    result = detect_ui_state(
                        foreground_app=foreground_app,
                        window_views_zip=zip_bytes,
                        visible_components=visible_components,
                    )
                    return AppStateData(
                        ui_state=str(result.get("ui_state") or UI_STATE_IN_APP),
                        input_required=bool(result.get("input_required")),
                        debug={**debug, **(result.get("debug") or {})},
                    )

                if foreground_app and foreground_app != _PRIME_PACKAGE:
                    return AppStateData(
                        ui_state=UI_STATE_NOT_SUPPORTED,
                        input_required=False,
                        debug=debug,
                    )

                # Prime fallback when no foreground app from activity/view dump.
                if not foreground_app:
                    surfaceflinger = self._client.shell(
                        "dumpsys SurfaceFlinger", timeout_s=30.0
                    )
                    if not zip_bytes and not (surfaceflinger or "").strip():
                        return AppStateData(
                            ui_state=UI_STATE_OFF,
                            input_required=False,
                            debug={"error": "empty_adb_dumps"},
                        )
                    if prime_video.is_prime_present(surfaceflinger):
                        result = prime_video.detect_ui_state(
                            surfaceflinger_dump=surfaceflinger
                        )
                        return AppStateData(
                            ui_state=str(result.get("ui_state") or UI_STATE_IN_APP),
                            input_required=bool(result.get("input_required")),
                            debug={
                                **debug,
                                **(result.get("debug") or {}),
                                "foreground_app": _PRIME_PACKAGE,
                            },
                        )

            if foreground_app == _DISNEY_PACKAGE:
                view_b64 = self._client.shell(
                    "cmd window dump-visible-window-views | base64", timeout_s=15.0
                )
                zip_bytes = base64.b64decode(view_b64)

                debug["window_views_zip_len"] = len(zip_bytes)
                debug["screen_id"] = hashlib.sha1(zip_bytes).hexdigest()[:12]

                visible_components = parse_visible_components_from_window_views_zip(
                    zip_bytes
                )
                debug["visible_components"] = visible_components

                result = detect_ui_state(
                    foreground_app=foreground_app,
                    window_views_zip=zip_bytes,
                    visible_components=visible_components,
                )

                return AppStateData(
                    ui_state=str(result.get("ui_state") or UI_STATE_IN_APP),
                    input_required=bool(result.get("input_required")),
                    debug={**debug, **(result.get("debug") or {})},
                )

            if foreground_app == _PRIME_PACKAGE:
                surfaceflinger = self._client.shell(
                    "dumpsys SurfaceFlinger", timeout_s=30.0
                )
                result = prime_video.detect_ui_state(surfaceflinger_dump=surfaceflinger)
                return AppStateData(
                    ui_state=str(result.get("ui_state") or UI_STATE_IN_APP),
                    input_required=bool(result.get("input_required")),
                    debug={**debug, **(result.get("debug") or {})},
                )

            if foreground_app:
                return AppStateData(
                    ui_state=UI_STATE_NOT_SUPPORTED,
                    input_required=False,
                    debug=debug,
                )

            return AppStateData(
                ui_state=UI_STATE_NOT_SUPPORTED,
                input_required=False,
                debug={**debug, "reason": "no_foreground_app"},
            )

        finally:
            self._client.close()
