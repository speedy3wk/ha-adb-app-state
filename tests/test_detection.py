"""Regression tests for screen detection using synthetic, non-personal data."""

import io
import zipfile

import pytest

from custom_components.adb_app_state.apps import (
    detect_ui_state,
    disney_plus,
    prime_video,
)
from custom_components.adb_app_state.const import (
    UI_STATE_CHOOSE_PROFILE,
    UI_STATE_ENTER_PIN,
    UI_STATE_HOME,
    UI_STATE_IN_APP,
    UI_STATE_MOVIE,
    UI_STATE_MOVIE_DETAIL,
    UI_STATE_NOT_SUPPORTED,
    UI_STATE_PREVIEW,
)
from custom_components.adb_app_state.view_dump import (
    iter_zip_entry_bytes,
    parse_primary_package_from_window_views_zip,
    parse_visible_components_from_window_views_zip,
)


def make_views(payload=b"", component="com.disney.disneyplus/MainActivity"):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(f"Window {component}", payload)
    return buffer.getvalue()


def prime_dump(*, hints="", frame="0 0 1920 1080", fps=""):
    return (
        "Display 0 HWC layers:\n"
        "SurfaceView com.amazon.amazonvideo.livingroom #1\n"
        f" | {frame} | {fps}\n"
        f"{hints}\n"
        "h/w composer state:\n"
    )


@pytest.mark.parametrize(
    ("marker", "state", "input_required"),
    [
        (b"profilesRoot", UI_STATE_CHOOSE_PROFILE, True),
        (b"pinCodeEditText", UI_STATE_ENTER_PIN, True),
        (b"detailRoot", UI_STATE_MOVIE_DETAIL, False),
        (b"globalNavContent", UI_STATE_HOME, False),
        (b"", UI_STATE_IN_APP, False),
        (b"fullScreenRoot content_title positive_button", UI_STATE_IN_APP, True),
    ],
)
def test_disney_markers(marker, state, input_required):
    result = disney_plus.detect_ui_state(
        window_views_zip=make_views(marker),
        visible_components=[f"{disney_plus.PACKAGE}/MainActivity"],
    )
    assert result["ui_state"] == state
    assert result["input_required"] is input_required


def test_disney_playback_and_pin_precedence():
    playback = [f"{disney_plus.PACKAGE}/TvPlaybackActivity"]
    assert (
        disney_plus.detect_ui_state(window_views_zip=b"", visible_components=playback)[
            "ui_state"
        ]
        == UI_STATE_MOVIE
    )
    assert (
        disney_plus.detect_ui_state(
            window_views_zip=make_views(b"enterPinRootView"),
            visible_components=playback,
        )["ui_state"]
        == UI_STATE_ENTER_PIN
    )


@pytest.mark.parametrize(
    ("dump", "state"),
    [
        ("", UI_STATE_IN_APP),
        ("No HWC section", UI_STATE_IN_APP),
        (prime_dump(), UI_STATE_IN_APP),
        (prime_dump(hints="hasProtectedContent=true"), UI_STATE_MOVIE),
        (prime_dump(hints="TRANSLATE"), UI_STATE_PREVIEW),
        (prime_dump(hints="geomLayerBounds=[0 0 1920 720]"), UI_STATE_PREVIEW),
        (prime_dump(fps="24.0fps active [test]"), UI_STATE_MOVIE),
        (
            prime_dump(frame="100 100 1800 800", fps="24.0fps active [test]"),
            UI_STATE_PREVIEW,
        ),
    ],
)
def test_prime_screens(dump, state):
    result = prime_video.detect_ui_state(surfaceflinger_dump=dump)
    assert result["ui_state"] == state
    assert result["input_required"] is False


@pytest.mark.parametrize(
    ("package", "state"),
    [(None, UI_STATE_IN_APP), ("org.example.unsupported", UI_STATE_NOT_SUPPORTED)],
)
def test_dispatch_fallback(package, state):
    assert (
        detect_ui_state(
            foreground_app=package, window_views_zip=b"", visible_components=[]
        )["ui_state"]
        == state
    )


@pytest.mark.parametrize("module", [disney_plus, prime_video])
def test_video_url_preserves_full_url(module):
    url = "https://example.test/video"
    assert module.build_video_url(f" {url} ") == url


def test_video_ids():
    assert disney_plus.build_video_url(" video-id ") == (
        "https://www.disneyplus.com/de-de/play/video-id"
    )
    assert prime_video.build_video_url(" ASIN ") == (
        "https://watch.amazon.de/watch?asin=ASIN"
    )


def test_view_zip_components_and_packages():
    data = make_views(b"com.disney.disneyplus:id/profilesRoot")
    assert parse_visible_components_from_window_views_zip(data) == [
        "com.disney.disneyplus/MainActivity"
    ]
    assert parse_primary_package_from_window_views_zip(data) == disney_plus.PACKAGE
    assert (
        parse_primary_package_from_window_views_zip(
            data, ignore_packages={disney_plus.PACKAGE}
        )
        is None
    )
    assert iter_zip_entry_bytes(data, max_bytes_per_file=3) == [b"com"]


def test_empty_and_malformed_view_zip():
    for data in (b"", b"not a zip"):
        assert iter_zip_entry_bytes(data) == []
        assert parse_visible_components_from_window_views_zip(data) == []
        assert parse_primary_package_from_window_views_zip(data) is None
