from __future__ import annotations

import asyncio
import re
import time
from typing import TYPE_CHECKING, Any

from ..const import UI_STATE_IN_APP, UI_STATE_MOVIE, UI_STATE_PREVIEW
from ..validation import TIMEOUT, prime_video
from .playback import (
    async_movie_is_stable,
    async_open_video,
    async_refresh_state,
    async_stop_app,
)

if TYPE_CHECKING:
    from ..coordinator import AdbAppStateCoordinator

PACKAGE = "com.amazon.amazonvideo.livingroom"
MAIN_ACTIVITY = "com.amazon.ignition.IgnitionActivity"

_HWC_SECTION_START_RE = re.compile(r"Display\s+0\s+HWC\s+layers:", re.IGNORECASE)
_HWC_SECTION_END_RE = re.compile(r"h/w\s+composer\s+state:", re.IGNORECASE)
_FPS_RE = re.compile(r"(?P<fps>[0-9.]+fps\s+[^\[]+)")


def _extract_hwc_section(text: str) -> str:
    start_m = _HWC_SECTION_START_RE.search(text or "")
    if not start_m:
        return ""
    end_m = _HWC_SECTION_END_RE.search(text, start_m.end())
    end = end_m.start() if end_m else len(text)
    return text[start_m.start() : end]


def _parse_prime_state_from_surfaceflinger(dump: str) -> tuple[str, dict[str, Any]]:
    debug: dict[str, Any] = {}
    hwc = _extract_hwc_section(dump)
    if not hwc:
        return UI_STATE_IN_APP, {"reason": "no_hwc"}

    lines = hwc.splitlines()
    for i, line in enumerate(lines):
        if "SurfaceView" not in line:
            continue
        if "amazon.amazonvideo" not in line:
            continue

        idx_match = re.search(r"#(\d+)", line)
        if not idx_match:
            continue
        if idx_match.group(1) != "1":
            continue

        row = lines[i + 1] if i + 1 < len(lines) else ""
        fr_match = _FPS_RE.search(row)
        frame_rate = (fr_match.group("fps") if fr_match else "").strip()
        debug["frame_rate"] = frame_rate or "none"

        # Parse display frame from row segments
        disp_l = disp_t = disp_r = disp_b = -1
        if "|" in row:
            parts = [p.strip() for p in row.split("|")]
            for segment in parts:
                nums = segment.split()
                if len(nums) >= 4 and all(n.isdigit() for n in nums[:4]):
                    disp_l, disp_t, disp_r, disp_b = map(int, nums[:4])
                    debug["disp_frame"] = f"{disp_l},{disp_t},{disp_r},{disp_b}"
                    break

        # Scan following lines for extra hints (protected content, translate, bounds)
        protected = False
        translate = False
        bounds_h = None
        for j in range(i + 1, min(i + 40, len(lines))):
            l2 = lines[j]
            if j != i + 1 and "SurfaceView" in l2 and "amazon.amazonvideo" in l2:
                break
            if "hasProtectedContent=true" in l2:
                protected = True
            if "TRANSLATE" in l2:
                translate = True
            if "geomLayerBounds=" in l2:
                m = re.search(
                    r"geomLayerBounds=\[[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+(?P<h>[0-9.]+)\]",
                    l2,
                )
                if m:
                    try:
                        bounds_h = float(m.group("h"))
                    except ValueError:
                        pass

        debug["protected"] = protected
        if bounds_h is not None:
            debug["bounds_h"] = int(bounds_h)
        debug["translate"] = translate

        if protected:
            return UI_STATE_MOVIE, debug
        if translate or (bounds_h is not None and bounds_h < 900):
            return UI_STATE_PREVIEW, debug
        if frame_rate:
            full_frame = (
                disp_l == 0 and disp_t == 0 and disp_r == 1920 and disp_b == 1080
            )
            return (UI_STATE_MOVIE if full_frame else UI_STATE_PREVIEW), debug

        return UI_STATE_IN_APP, debug

    return UI_STATE_IN_APP, {"reason": "no_prime_layers"}


def is_prime_present(surfaceflinger_dump: str) -> bool:
    return "amazon.amazonvideo" in (surfaceflinger_dump or "")


def detect_ui_state(
    *,
    window_views_zip: bytes | None = None,
    visible_components: list[str] | None = None,
    surfaceflinger_dump: str | None = None,
) -> dict[str, Any]:
    """Prime Video UI state detection.

    Prime uses SurfaceView and often hides view hierarchies during DRM. We parse the
    SurfaceFlinger HWC section to distinguish PREVIEW vs MOVIE when possible.
    """

    _ = window_views_zip
    _ = visible_components

    if surfaceflinger_dump:
        state, dbg = _parse_prime_state_from_surfaceflinger(surfaceflinger_dump)
        return {"ui_state": state, "input_required": False, "debug": dbg}

    return {
        "ui_state": UI_STATE_IN_APP,
        "input_required": False,
        "debug": {"reason": "no_surfaceflinger"},
    }


def build_video_url(film_asin: str) -> str:
    value = prime_video(film_asin)
    if value.startswith("https://"):
        return value
    return f"https://watch.amazon.de/watch?asin={value}"


async def prepare_movie(
    *,
    coordinator: AdbAppStateCoordinator,
    film_asin: str,
    auto_login: bool,
    pause_on_start: bool,
    timeout_s: int,
) -> None:
    """Best-effort Prime automation: open video, optional auto-login, optional pause on movie."""

    url = build_video_url(film_asin)
    timeout_s = TIMEOUT(timeout_s)

    async def refresh_state() -> str:
        return (await async_refresh_state(coordinator)).ui_state

    async def key(code: str) -> None:
        await coordinator.async_shell(f"input keyevent {code}", timeout_s=5.0)

    async def media(cmd: str) -> None:
        await coordinator.async_shell(
            f"cmd media_session dispatch {cmd}", timeout_s=5.0
        )

    deadline = time.monotonic() + timeout_s
    sent_login = False

    await async_stop_app(coordinator, PACKAGE)
    await async_open_video(
        coordinator, url=url, package=PACKAGE, activity=MAIN_ACTIVITY, clear_task=True
    )

    while time.monotonic() < deadline:
        state = await refresh_state()

        if state == UI_STATE_IN_APP and auto_login and not sent_login:
            await key("KEYCODE_DPAD_CENTER")
            sent_login = True
            continue

        if state == UI_STATE_MOVIE:
            if not await async_movie_is_stable(coordinator, PACKAGE):
                continue
            if time.monotonic() >= deadline:
                break
            if pause_on_start:
                await media("pause")
            return

        await asyncio.sleep(0.5)

    raise TimeoutError("Timed out preparing Prime Video movie")
