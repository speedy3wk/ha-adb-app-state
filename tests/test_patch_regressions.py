"""Reproduce the v0.1.0 connection, input and false-success bugs."""

import asyncio
import threading
from unittest.mock import AsyncMock, Mock, patch

import probatio as vol
import pytest

from custom_components.adb_app_state import (
    SERVICE_SCHEMA_MEDIA_DISPATCH,
    SERVICE_SCHEMA_PREPARE_DISNEY,
    SERVICE_SCHEMA_PREPARE_PRIME,
)
from custom_components.adb_app_state.apps import disney_plus, prime_video
from custom_components.adb_app_state.const import UI_STATE_MOVIE

from .test_prepare import fake_coordinator, screen

DISNEY_ID = "ab7c4e29-04f1-46dd-931a-d43be1ce0f8c"
PRIME_ID = "B0B5NPCSZX"


async def test_poll_and_command_never_share_an_open_connection(coordinator):
    entered = threading.Event()
    release = threading.Event()
    overlapping = threading.Event()
    connected = False

    def connect():
        nonlocal connected
        if connected:
            overlapping.set()
        connected = True

    def close():
        nonlocal connected
        connected = False

    def shell(command, **kwargs):
        if command == "dumpsys activity activities":
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release the simulated poll")
            return "mResumedActivity: ActivityRecord{42 u0 org.example.app/.Main t1}"
        return "ok"

    client = Mock(connect=connect, close=close, shell=shell)
    with patch.object(coordinator, "_client", client):
        poll = asyncio.create_task(coordinator._async_update_data())
        command = None
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            command = asyncio.create_task(coordinator.async_shell("echo ok"))
            # A queued command must not connect while the poll owns the client.
            await asyncio.to_thread(overlapping.wait, 0.1)
            assert not overlapping.is_set()
        finally:
            release.set()
            await poll
            if command is not None:
                await command


async def test_cancellation_keeps_worker_connection_locked(coordinator):
    entered = threading.Event()
    release = threading.Event()
    overlapping = threading.Event()
    connected = False

    def connect():
        nonlocal connected
        if connected:
            overlapping.set()
        connected = True

    def close():
        nonlocal connected
        connected = False

    def shell(command, **kwargs):
        if command == "blocked":
            entered.set()
            if not release.wait(5):
                raise TimeoutError("Test did not release the command")
        return "ok"

    with patch.object(
        coordinator, "_client", Mock(connect=connect, close=close, shell=shell)
    ):
        first = asyncio.create_task(coordinator.async_shell("blocked"))
        second = None
        try:
            assert await asyncio.to_thread(entered.wait, 5)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            second = asyncio.create_task(coordinator.async_shell("echo ok"))
            await asyncio.to_thread(overlapping.wait, 0.1)
            assert not overlapping.is_set()
        finally:
            release.set()
            if not first.done():
                await first
            if second is not None:
                assert await second == "ok"


@pytest.mark.parametrize(
    ("schema", "data"),
    [
        (SERVICE_SCHEMA_PREPARE_DISNEY, {"film_id": ""}),
        (SERVICE_SCHEMA_PREPARE_DISNEY, {"film_id": "not-a-uuid"}),
        (SERVICE_SCHEMA_PREPARE_DISNEY, {"film_id": DISNEY_ID, "pin": "12x4"}),
        (SERVICE_SCHEMA_PREPARE_DISNEY, {"film_id": DISNEY_ID, "pin": "１２３４"}),
        (SERVICE_SCHEMA_PREPARE_DISNEY, {"film_id": DISNEY_ID, "profile_index": -1}),
        (SERVICE_SCHEMA_PREPARE_DISNEY, {"film_id": DISNEY_ID, "profile_index": 11}),
        (SERVICE_SCHEMA_PREPARE_DISNEY, {"film_id": DISNEY_ID, "timeout": 9}),
        (SERVICE_SCHEMA_PREPARE_PRIME, {"film_asin": PRIME_ID, "timeout": 601}),
        (SERVICE_SCHEMA_PREPARE_PRIME, {"film_asin": "not-an-asin"}),
        (SERVICE_SCHEMA_PREPARE_PRIME, {"film_asin": "https://example.test/video"}),
        (SERVICE_SCHEMA_PREPARE_PRIME, {"film_asin": "https://amazon.de.evil.test/a"}),
        (
            SERVICE_SCHEMA_PREPARE_DISNEY,
            {"film_id": "https://disneyplus.com@evil.test/a"},
        ),
        (SERVICE_SCHEMA_MEDIA_DISPATCH, {"key": "play", "times": 0}),
        (SERVICE_SCHEMA_MEDIA_DISPATCH, {"key": "play", "times": 201}),
        (SERVICE_SCHEMA_MEDIA_DISPATCH, {"key": "play", "delay_ms": -1}),
        (SERVICE_SCHEMA_MEDIA_DISPATCH, {"key": "play", "delay_ms": 2001}),
    ],
)
def test_invalid_action_inputs_are_rejected(schema, data):
    with pytest.raises(vol.Invalid):
        schema(data)


@pytest.mark.parametrize("module", [disney_plus, prime_video])
async def test_failed_android_launch_cannot_report_success(module):
    coordinator = fake_coordinator(
        [screen(UI_STATE_MOVIE), screen(UI_STATE_MOVIE)], module.PACKAGE
    )
    coordinator.data = screen(UI_STATE_MOVIE, foreground_app=module.PACKAGE)
    coordinator.async_shell.side_effect = [
        "adb_app_state_stopped",
        "Error: Activity not started",
    ]
    fields = (
        {"film_id": DISNEY_ID, "profile_index": None, "pin": None}
        if module is disney_plus
        else {"film_asin": PRIME_ID, "auto_login": False}
    )
    with patch.object(module.asyncio, "sleep", new_callable=AsyncMock):
        with pytest.raises(RuntimeError, match="confirm launching"):
            await module.prepare_movie(
                coordinator=coordinator,
                pause_on_start=True,
                timeout_s=90,
                **fields,
            )
    assert not any(
        call.args[0] == "cmd media_session dispatch pause"
        for call in coordinator.async_shell.await_args_list
    )
