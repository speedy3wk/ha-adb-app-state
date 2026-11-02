"""Verify navigation actions without sending commands to a device."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from custom_components.adb_app_state.apps import disney_plus, prime_video
from custom_components.adb_app_state.const import (
    UI_STATE_CHOOSE_PROFILE,
    UI_STATE_ENTER_PIN,
    UI_STATE_IN_APP,
    UI_STATE_MOVIE,
)


def fake_coordinator(states):
    coordinator = SimpleNamespace(
        data=None,
        async_shell=AsyncMock(),
        async_request_refresh=AsyncMock(),
    )
    remaining = iter(states)

    async def refresh():
        coordinator.data = next(remaining)

    coordinator.async_request_refresh.side_effect = refresh
    return coordinator


def screen(state, **debug):
    return SimpleNamespace(ui_state=state, debug=debug)


async def test_disney_profile_pin_and_pause():
    coordinator = fake_coordinator(
        [
            screen(UI_STATE_CHOOSE_PROFILE),
            screen(UI_STATE_ENTER_PIN),
            screen(UI_STATE_MOVIE),
            screen(UI_STATE_MOVIE),
        ]
    )
    with patch.object(disney_plus.asyncio, "sleep", new_callable=AsyncMock):
        await disney_plus.prepare_movie(
            coordinator=coordinator,
            film_id="test-video",
            profile_index=1,
            pin="12",
            pause_on_start=True,
            timeout_s=90,
        )
    commands = [call.args[0] for call in coordinator.async_shell.await_args_list]
    assert "https://www.disneyplus.com/de-de/play/test-video" in commands[0]
    assert commands[1:] == [
        "input keyevent KEYCODE_DPAD_RIGHT",
        "input keyevent KEYCODE_DPAD_CENTER",
        "input keyevent KEYCODE_1",
        "input keyevent KEYCODE_2",
        "input keyevent KEYCODE_DPAD_CENTER",
        "cmd media_session dispatch pause",
    ]


async def test_disney_reports_error_dialog():
    coordinator = fake_coordinator([screen(UI_STATE_IN_APP, has_error_dialog=True)])
    with pytest.raises(RuntimeError, match="deep link failed"):
        await disney_plus.prepare_movie(
            coordinator=coordinator,
            film_id="test-video",
            profile_index=None,
            pin=None,
            pause_on_start=False,
            timeout_s=90,
        )
    coordinator.async_shell.assert_awaited_with(
        "input keyevent KEYCODE_DPAD_CENTER", timeout_s=5.0
    )


@pytest.mark.parametrize("auto_login", [False, True])
async def test_prime_login_and_pause(auto_login):
    states = [screen(UI_STATE_IN_APP), screen(UI_STATE_MOVIE)]
    coordinator = fake_coordinator(states)
    with patch.object(prime_video.asyncio, "sleep", new_callable=AsyncMock):
        await prime_video.prepare_movie(
            coordinator=coordinator,
            film_asin="TESTASIN",
            auto_login=auto_login,
            pause_on_start=True,
            timeout_s=90,
        )
    commands = [call.args[0] for call in coordinator.async_shell.await_args_list]
    assert "https://watch.amazon.de/watch?asin=TESTASIN" in commands[0]
    assert ("input keyevent KEYCODE_DPAD_CENTER" in commands) is auto_login
    assert commands[-1] == "cmd media_session dispatch pause"


@pytest.mark.parametrize("module", [disney_plus, prime_video])
async def test_prepare_timeout_is_reported(module):
    coordinator = fake_coordinator([])
    fields = (
        {"film_id": "test-video", "profile_index": None, "pin": None}
        if module is disney_plus
        else {"film_asin": "TESTASIN", "auto_login": False}
    )
    times = [100.0, 100.0, 1000.0] if module is disney_plus else [100.0, 1000.0]
    with patch.object(module.time, "monotonic", side_effect=times):
        with pytest.raises(TimeoutError, match="Timed out"):
            await module.prepare_movie(
                coordinator=coordinator,
                pause_on_start=False,
                timeout_s=90,
                **fields,
            )
