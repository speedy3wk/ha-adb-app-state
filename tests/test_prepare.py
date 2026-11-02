"""Verify navigation actions without sending commands to a device."""

import shlex
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.adb_app_state.apps import disney_plus, prime_video
from custom_components.adb_app_state.apps.playback import (
    async_open_video,
    async_refresh_state,
    async_stop_app,
)
from custom_components.adb_app_state.const import (
    UI_STATE_CHOOSE_PROFILE,
    UI_STATE_ENTER_PIN,
    UI_STATE_IN_APP,
    UI_STATE_MOVIE,
    UI_STATE_NOT_SUPPORTED,
    UI_STATE_OFF,
)
from custom_components.adb_app_state.coordinator import AppStateData

DISNEY_ID = "ab7c4e29-04f1-46dd-931a-d43be1ce0f8c"
PRIME_ID = "B0B5NPCSZX"


def fake_coordinator(states, package=disney_plus.PACKAGE):
    async def shell(command, **kwargs):
        if command.startswith("am force-stop "):
            return "adb_app_state_stopped"
        if command.startswith("am start "):
            return f"Status: ok\nActivity: {package}/MainActivity\nComplete"
        return ""

    coordinator = SimpleNamespace(
        data=None,
        last_update_success=True,
        async_shell=AsyncMock(side_effect=shell),
        async_refresh=AsyncMock(),
        async_request_refresh=AsyncMock(),
    )
    remaining = iter(
        [screen(UI_STATE_NOT_SUPPORTED, foreground_app="org.example.launcher"), *states]
    )

    async def refresh():
        coordinator.data = next(remaining)
        coordinator.data.debug.setdefault("foreground_app", package)

    coordinator.async_refresh.side_effect = refresh
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
            film_id=DISNEY_ID,
            profile_index=1,
            pin="12",
            pause_on_start=True,
            timeout_s=90,
        )
    commands = [call.args[0] for call in coordinator.async_shell.await_args_list]
    assert commands[0].startswith(f"am force-stop {disney_plus.PACKAGE}")
    assert f"https://www.disneyplus.com/de-de/play/{DISNEY_ID}" in commands[1]
    assert commands[2:] == [
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
            film_id=DISNEY_ID,
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
    states = [screen(UI_STATE_IN_APP), screen(UI_STATE_MOVIE), screen(UI_STATE_MOVIE)]
    coordinator = fake_coordinator(states, prime_video.PACKAGE)
    with patch.object(prime_video.asyncio, "sleep", new_callable=AsyncMock):
        await prime_video.prepare_movie(
            coordinator=coordinator,
            film_asin=PRIME_ID,
            auto_login=auto_login,
            pause_on_start=True,
            timeout_s=90,
        )
    commands = [call.args[0] for call in coordinator.async_shell.await_args_list]
    assert commands[0].startswith(f"am force-stop {prime_video.PACKAGE}")
    assert f"https://watch.amazon.de/watch?asin={PRIME_ID}" in commands[1]
    assert ("input keyevent KEYCODE_DPAD_CENTER" in commands) is auto_login
    assert commands[-1] == "cmd media_session dispatch pause"


@pytest.mark.parametrize("module", [disney_plus, prime_video])
async def test_prepare_timeout_is_reported(module):
    fields = (
        {"film_id": DISNEY_ID, "profile_index": None, "pin": None}
        if module is disney_plus
        else {"film_asin": PRIME_ID, "auto_login": False}
    )
    times = [100.0, 100.0, 1000.0] if module is disney_plus else [100.0, 1000.0]
    coordinator = fake_coordinator([], module.PACKAGE)
    with patch.object(
        module, "time", SimpleNamespace(monotonic=Mock(side_effect=times))
    ):
        with pytest.raises(TimeoutError, match="Timed out"):
            await module.prepare_movie(
                coordinator=coordinator,
                pause_on_start=False,
                timeout_s=90,
                **fields,
            )


@pytest.mark.parametrize("module", [disney_plus, prime_video])
async def test_still_running_app_cannot_be_accepted_as_fresh_playback(module):
    coordinator = fake_coordinator([], module.PACKAGE)
    coordinator.async_refresh.side_effect = None
    coordinator.data = screen(UI_STATE_MOVIE, foreground_app=module.PACKAGE)
    with pytest.raises(RuntimeError, match="did not stop"):
        await async_stop_app(coordinator, module.PACKAGE)
    assert coordinator.async_shell.await_count == 1
    assert coordinator.async_shell.await_args.args[0].startswith("am force-stop ")


@pytest.mark.parametrize(
    "output",
    [
        "",
        "Status: timeout\nActivity: com.disney.disneyplus/MainActivity",
        "Status: ok\nActivity: org.example.other/MainActivity",
        "Status: ok",
        "Status: ok\nActivity: com.disney.disneyplus/MainActivity\nError: launch failed",
        "Status: ok\nActivity: com.disney.disneyplus/MainActivity\n"
        "Warning: Activity not started, intent has been delivered",
    ],
)
async def test_android_launch_requires_successful_status_and_target_activity(output):
    coordinator = fake_coordinator([])
    coordinator.async_shell.side_effect = None
    coordinator.async_shell.return_value = output
    with pytest.raises(RuntimeError, match="confirm launching"):
        await async_open_video(
            coordinator,
            url=disney_plus.build_video_url(DISNEY_ID),
            package=disney_plus.PACKAGE,
            activity=disney_plus.MAIN_ACTIVITY,
            clear_task=True,
        )


async def test_deep_link_is_one_shell_argument():
    coordinator = fake_coordinator([])
    url = "https://www.disneyplus.com/video/it's?x=1&y=two"
    await async_open_video(
        coordinator,
        url=disney_plus.build_video_url(url),
        package=disney_plus.PACKAGE,
        activity=disney_plus.MAIN_ACTIVITY,
        clear_task=True,
    )
    arguments = shlex.split(coordinator.async_shell.await_args.args[0])
    assert arguments[arguments.index("-d") + 1] == url
    assert arguments == [
        "am",
        "start",
        "-W",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        url,
        "-n",
        f"{disney_plus.PACKAGE}/{disney_plus.MAIN_ACTIVITY}",
        "-f",
        "0x10008000",
    ]


@pytest.mark.parametrize("module", [disney_plus, prime_video])
async def test_transient_movie_never_triggers_early_pause(module):
    coordinator = fake_coordinator(
        [
            screen(UI_STATE_MOVIE),
            screen(UI_STATE_IN_APP),
            screen(UI_STATE_MOVIE),
            screen(UI_STATE_MOVIE),
        ],
        module.PACKAGE,
    )
    fields = (
        {"film_id": DISNEY_ID, "profile_index": None, "pin": None}
        if module is disney_plus
        else {"film_asin": PRIME_ID, "auto_login": False}
    )
    with patch.object(module.asyncio, "sleep", new_callable=AsyncMock):
        await module.prepare_movie(
            coordinator=coordinator, pause_on_start=True, timeout_s=90, **fields
        )
    assert coordinator.async_refresh.await_count == 5
    assert [call.args[0] for call in coordinator.async_shell.await_args_list][2:] == [
        "cmd media_session dispatch pause"
    ]
    coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.parametrize("state", [UI_STATE_MOVIE, UI_STATE_OFF])
async def test_unavailable_or_stale_data_is_not_playback_confirmation(state):
    coordinator = fake_coordinator([])
    coordinator.data = screen(state, foreground_app=disney_plus.PACKAGE)
    coordinator.last_update_success = state != UI_STATE_MOVIE
    coordinator.async_refresh.side_effect = None
    with pytest.raises(RuntimeError):
        await async_refresh_state(coordinator)


async def test_missing_pin_is_explicit_error_not_empty_submit():
    coordinator = fake_coordinator([screen(UI_STATE_ENTER_PIN)])
    with pytest.raises(RuntimeError, match="requires a PIN"):
        await disney_plus.prepare_movie(
            coordinator=coordinator,
            film_id=DISNEY_ID,
            profile_index=None,
            pin=None,
            pause_on_start=False,
            timeout_s=90,
        )
    assert coordinator.async_shell.await_count == 2


@pytest.mark.parametrize("module", [disney_plus, prime_video])
async def test_preparation_with_real_coordinator_refreshes(coordinator, module):
    fields = (
        {"film_id": DISNEY_ID, "profile_index": None, "pin": None}
        if module is disney_plus
        else {"film_asin": PRIME_ID, "auto_login": False}
    )
    with (
        patch.object(
            coordinator,
            "_poll_sync",
            side_effect=[
                AppStateData(
                    UI_STATE_NOT_SUPPORTED,
                    False,
                    {"foreground_app": "org.example.launcher"},
                ),
                AppStateData(UI_STATE_MOVIE, False, {"foreground_app": module.PACKAGE}),
                AppStateData(UI_STATE_MOVIE, False, {"foreground_app": module.PACKAGE}),
            ],
        ) as poll,
        patch.object(
            coordinator,
            "async_shell",
            side_effect=[
                "adb_app_state_stopped",
                f"Status: ok\nActivity: {module.PACKAGE}/{module.MAIN_ACTIVITY}",
                "",
            ],
        ) as shell,
        patch.object(module.asyncio, "sleep", new_callable=AsyncMock),
    ):
        await module.prepare_movie(
            coordinator=coordinator, pause_on_start=True, timeout_s=90, **fields
        )
    assert poll.call_count == 3
    shell.assert_awaited_with("cmd media_session dispatch pause", timeout_s=5.0)
    coordinator.async_request_refresh.assert_not_awaited()
