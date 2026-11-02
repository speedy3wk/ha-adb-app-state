from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from ..const import (
    UI_STATE_CHOOSE_PROFILE,
    UI_STATE_ENTER_PIN,
    UI_STATE_HOME,
    UI_STATE_IN_APP,
    UI_STATE_MOVIE,
    UI_STATE_MOVIE_DETAIL,
)
from ..validation import PROFILE_INDEX, TIMEOUT, disney_video
from ..validation import pin as validate_pin
from ..view_dump import iter_zip_entry_bytes
from .playback import (
    async_movie_is_stable,
    async_open_video,
    async_refresh_state,
    async_stop_app,
)

if TYPE_CHECKING:
    from ..coordinator import AdbAppStateCoordinator

PACKAGE = "com.disney.disneyplus"
MAIN_ACTIVITY = "com.bamtechmedia.dominguez.main.MainActivity"


def detect_ui_state(
    *, window_views_zip: bytes, visible_components: list[str]
) -> dict[str, Any]:
    debug: dict[str, Any] = {}

    tv_playback_component = any(
        "TvPlaybackActivity" in (c or "") for c in visible_components
    )
    main_component = any("MainActivity" in (c or "") for c in visible_components)
    debug["tv_playback_component"] = tv_playback_component
    debug["main_component"] = main_component

    blobs = iter_zip_entry_bytes(
        window_views_zip, max_files=10, max_bytes_per_file=120_000
    )
    joined = b"".join(blobs)

    has_pin = (
        b"enterPinRootView" in joined
        or b"pinCodeEditText" in joined
        or b"disneyPinCode" in joined
    )
    has_profiles = b"profilesRoot" in joined or b"profilesContent" in joined
    has_detail = (
        b"detailRoot" in joined
        or b"detailTitleTextView" in joined
        or b"detailAllButtonsRoot" in joined
        or b"detailPageMainButton" in joined
    )
    has_home = (
        b"globalNavContent" in joined
        or b"shelfViewPagerContainer" in joined
        or b"collectionRecyclerView" in joined
    )
    has_error_dialog = (
        b"fullScreenRoot" in joined
        and b"content_title" in joined
        and b"positive_button" in joined
    )

    debug["has_pin"] = has_pin
    debug["has_profiles"] = has_profiles
    debug["has_detail"] = has_detail
    debug["has_home"] = has_home
    debug["has_error_dialog"] = has_error_dialog

    # Error dialog: user must dismiss (OK). Treat as in-app but input required.
    if has_error_dialog:
        return {"ui_state": UI_STATE_IN_APP, "input_required": True, "debug": debug}

    # 1) PLAYING: require TvPlaybackActivity, but avoid transient false positives
    # during login/home transitions where Disney may briefly create the playback activity.
    if tv_playback_component and not (
        has_pin or has_profiles or has_home or has_detail
    ):
        return {"ui_state": UI_STATE_MOVIE, "input_required": False, "debug": debug}
    # Fallback: if payload is empty/minimal but MainActivity is not visible, trust TvPlaybackActivity.
    if tv_playback_component and not main_component and not (has_pin or has_profiles):
        return {"ui_state": UI_STATE_MOVIE, "input_required": False, "debug": debug}

    # 2) Strong Disney markers
    if has_pin:
        return {"ui_state": UI_STATE_ENTER_PIN, "input_required": True, "debug": debug}

    if has_profiles:
        return {
            "ui_state": UI_STATE_CHOOSE_PROFILE,
            "input_required": True,
            "debug": debug,
        }

    # 3) Detail markers
    if has_detail:
        return {
            "ui_state": UI_STATE_MOVIE_DETAIL,
            "input_required": False,
            "debug": debug,
        }

    # 4) Home markers
    if has_home:
        return {"ui_state": UI_STATE_HOME, "input_required": False, "debug": debug}

    return {"ui_state": UI_STATE_IN_APP, "input_required": False, "debug": debug}


def build_video_url(film_id: str) -> str:
    # Accept either a UUID or a full Disney+ URL.
    value = disney_video(film_id)
    if value.startswith("https://"):
        return value
    # On this Android TV, the /de-de/play/<id> pattern is reliable, while /video/<id>
    # can trigger an in-app error dialog.
    return f"https://www.disneyplus.com/de-de/play/{value}"


async def prepare_movie(
    *,
    coordinator: AdbAppStateCoordinator,
    film_id: str,
    profile_index: int | None,
    pin: str | None,
    pause_on_start: bool,
    timeout_s: int,
) -> None:
    """Best-effort automation: open film, optional profile/pin, start playback, pause.

    This is intentionally simple and relies on coordinator state detection.
    """

    url = build_video_url(film_id)
    timeout_s = TIMEOUT(timeout_s)
    if profile_index is not None:
        profile_index = PROFILE_INDEX(profile_index)
    if pin is not None:
        pin = validate_pin(pin)

    async def open_video(*, clear_task: bool) -> None:
        await async_open_video(
            coordinator,
            url=url,
            package=PACKAGE,
            activity=MAIN_ACTIVITY,
            clear_task=clear_task,
        )

    deadline = time.monotonic() + timeout_s

    async def refresh_state() -> str:
        return (await async_refresh_state(coordinator)).ui_state

    def has_error_dialog() -> bool:
        data = getattr(coordinator, "data", None)
        dbg = getattr(data, "debug", None) if data else None
        return bool(dbg and dbg.get("has_error_dialog"))

    async def key(code: str) -> None:
        await coordinator.async_shell(f"input keyevent {code}", timeout_s=5.0)

    async def media(cmd: str) -> None:
        # Dispatch media keys to the active session; works during DRM playback where UI is redacted.
        await coordinator.async_shell(
            f"cmd media_session dispatch {cmd}", timeout_s=5.0
        )

    async def type_pin(pin_value: str) -> None:
        for ch in pin_value:
            await key(f"KEYCODE_{ch}")

    started_playback = False
    deep_link_attempts = 0
    last_deep_link_ts = 0.0

    async def maybe_open_deep_link(*, clear_task: bool) -> None:
        nonlocal deep_link_attempts, last_deep_link_ts
        now = time.monotonic()
        if deep_link_attempts >= 4:
            return
        if now - last_deep_link_ts < 2.0:
            return
        deep_link_attempts += 1
        last_deep_link_ts = now
        await open_video(clear_task=clear_task)

    await async_stop_app(coordinator, PACKAGE)
    await open_video(clear_task=True)
    deep_link_attempts = 1
    last_deep_link_ts = time.monotonic()

    while time.monotonic() < deadline:
        state = await refresh_state()

        if has_error_dialog():
            # Disney shows an OK dialog ("Etwas ist schiefgelaufen...") when a deep link fails.
            # Dismiss it so the user isn't stuck, then abort.
            await key("KEYCODE_DPAD_CENTER")
            raise RuntimeError(
                "Disney+ returned an error dialog for this film_id (deep link failed)"
            )

        if state == UI_STATE_CHOOSE_PROFILE:
            # default: just select current profile; optional move right
            if profile_index is not None:
                for _ in range(profile_index):
                    await key("KEYCODE_DPAD_RIGHT")
            await key("KEYCODE_DPAD_CENTER")
            continue

        if state == UI_STATE_ENTER_PIN:
            if pin is None:
                raise RuntimeError(
                    "Disney+ requires a PIN; provide the pin action field"
                )
            await type_pin(pin)
            await key("KEYCODE_DPAD_CENTER")
            # Give the app a moment to transition after PIN.
            await asyncio.sleep(0.6)
            continue

        if state == UI_STATE_MOVIE_DETAIL:
            # Usually play button is focused.
            await key("KEYCODE_DPAD_CENTER")
            started_playback = True
            continue

        if state == UI_STATE_MOVIE:
            if not await async_movie_is_stable(coordinator, PACKAGE):
                continue
            if time.monotonic() >= deadline:
                break
            if pause_on_start:
                await media("pause")

            return

        # If we land on HOME/IN_APP instead of the requested movie, re-issue the deep link.
        if state in (UI_STATE_HOME, UI_STATE_IN_APP) and not started_playback:
            await maybe_open_deep_link(clear_task=deep_link_attempts >= 2)

        await asyncio.sleep(0.4)

    raise TimeoutError("Timed out preparing Disney+ movie")
