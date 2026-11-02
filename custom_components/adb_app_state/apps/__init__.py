from __future__ import annotations

from typing import Any

from ..const import UI_STATE_IN_APP, UI_STATE_NOT_SUPPORTED
from . import disney_plus, prime_video


def detect_ui_state(
    *,
    foreground_app: str | None,
    window_views_zip: bytes,
    visible_components: list[str],
) -> dict[str, Any]:
    """Return dict with ui_state/input_required/debug.

    App-agnostic dispatcher. Each app module owns its package constant + detection.
    """

    if not foreground_app:
        return {
            "ui_state": UI_STATE_IN_APP,
            "input_required": False,
            "debug": {"reason": "no_foreground_app"},
        }

    if foreground_app == disney_plus.PACKAGE:
        return disney_plus.detect_ui_state(
            window_views_zip=window_views_zip, visible_components=visible_components
        )

    if foreground_app == prime_video.PACKAGE:
        return prime_video.detect_ui_state(
            window_views_zip=window_views_zip, visible_components=visible_components
        )

    return {
        "ui_state": UI_STATE_NOT_SUPPORTED,
        "input_required": False,
        "debug": {"foreground_app": foreground_app},
    }
