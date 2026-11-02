"""Require a fresh, acknowledged app launch before accepting playback."""

import asyncio
import re
from shlex import quote
from typing import TYPE_CHECKING

from ..const import UI_STATE_MOVIE, UI_STATE_OFF

if TYPE_CHECKING:
    from ..coordinator import AdbAppStateCoordinator, AppStateData

_STOPPED = "adb_app_state_stopped"


async def async_refresh_state(coordinator: AdbAppStateCoordinator) -> AppStateData:
    # A debounced refresh request can reuse a poll started before a navigation command.
    await coordinator.async_refresh()
    if not coordinator.last_update_success or coordinator.data is None:
        raise RuntimeError("Unable to refresh the Android TV state")
    if coordinator.data.ui_state == UI_STATE_OFF:
        raise RuntimeError("ADB became unavailable while preparing the movie")
    return coordinator.data


async def async_stop_app(coordinator: AdbAppStateCoordinator, package: str) -> None:
    output = await coordinator.async_shell(
        f"am force-stop {package} && echo {_STOPPED}", timeout_s=8.0
    )
    if output.strip() != _STOPPED:
        raise RuntimeError("Android did not confirm stopping the streaming app")
    data = await async_refresh_state(coordinator)
    foreground = data.debug.get("foreground_app")
    if foreground == package or (data.ui_state == UI_STATE_MOVIE and not foreground):
        raise RuntimeError("The streaming app did not stop; refusing stale playback")


async def async_open_video(
    coordinator: AdbAppStateCoordinator,
    *,
    url: str,
    package: str,
    activity: str,
    clear_task: bool,
) -> None:
    flags = "0x10008000" if clear_task else "0x10000000"
    output = await coordinator.async_shell(
        f"am start -W -a android.intent.action.VIEW -d {quote(url)} "
        f"-n {package}/{activity} -f {flags}",
        timeout_s=12.0,
    )
    if (
        not re.search(r"^\s*Status:\s*ok\s*$", output, re.MULTILINE)
        or not re.search(
            rf"^\s*Activity:\s*{re.escape(package)}/\S+\s*$", output, re.MULTILINE
        )
        or re.search(
            r"^\s*(?:Error\b|Exception\b|Warning:\s*Activity not started)",
            output,
            re.MULTILINE | re.IGNORECASE,
        )
    ):
        raise RuntimeError("Android did not confirm launching the requested deep link")


async def async_movie_is_stable(
    coordinator: AdbAppStateCoordinator, package: str
) -> bool:
    if (
        coordinator.data is None
        or coordinator.data.ui_state != UI_STATE_MOVIE
        or coordinator.data.debug.get("foreground_app") != package
    ):
        return False
    await asyncio.sleep(0.7)
    data = await async_refresh_state(coordinator)
    return (
        data.ui_state == UI_STATE_MOVIE and data.debug.get("foreground_app") == package
    )
