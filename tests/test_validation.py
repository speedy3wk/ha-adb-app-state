"""Verify input boundaries and trusted deep-link handling."""

import probatio as vol
import pytest

from custom_components.adb_app_state.validation import (
    DELAY_MS,
    PORT,
    PROFILE_INDEX,
    REPEAT_COUNT,
    SCAN_INTERVAL,
    TIMEOUT,
    disney_video,
    host,
    integer,
    pin,
    prime_video,
)


@pytest.mark.parametrize(
    ("validator", "low", "high"),
    [
        (PORT, 1, 65535),
        (PROFILE_INDEX, 0, 10),
        (REPEAT_COUNT, 1, 200),
        (DELAY_MS, 0, 2000),
        (TIMEOUT, 10, 600),
    ],
)
def test_integer_bounds(validator, low, high):
    assert validator(low) == low
    assert validator(str(high)) == high
    for value in (low - 1, high + 1):
        with pytest.raises(vol.Invalid):
            validator(value)


@pytest.mark.parametrize("value", [True, False, 1.5, 1.0, "1.5", "", None])
def test_integers_do_not_truncate_or_accept_booleans(value):
    with pytest.raises(vol.Invalid):
        integer(value)


def test_positive_scan_interval():
    assert SCAN_INTERVAL(1) == 1
    assert SCAN_INTERVAL(3600) == 3600
    with pytest.raises(vol.Invalid):
        SCAN_INTERVAL(0)
    with pytest.raises(vol.Invalid):
        SCAN_INTERVAL(-5)


@pytest.mark.parametrize(
    "value",
    ["127.0.0.1", "2001:db8::1", "shield", "android-tv.example.test", "SHIELD.local."],
)
def test_valid_hosts(value):
    assert host(f" {value} ") == value


@pytest.mark.parametrize(
    "value",
    ["", " ", "https://shield", "host:5555", "bad host", "-host", "999.1.1.1", "a..b"],
)
def test_invalid_hosts(value):
    with pytest.raises(vol.Invalid):
        host(value)


def test_pin_preserves_leading_zeroes():
    assert pin("0012") == "0012"


@pytest.mark.parametrize("value", ["", "12 34", "12x4", "１２３４", "١٢٣٤", 1234])
def test_invalid_pins(value):
    with pytest.raises(vol.Invalid):
        pin(value)


@pytest.mark.parametrize(
    ("validator", "url"),
    [
        (disney_video, "https://www.disneyplus.com/de-de/play/test?x=1&y=two"),
        (disney_video, "https://disneyplus.com/video/it's"),
        (prime_video, "https://watch.amazon.de/watch?asin=B0B5NPCSZX"),
        (prime_video, "https://www.primevideo.com/detail/B0B5NPCSZX"),
        (prime_video, "https://www.amazon.co.uk/gp/video/detail/B0B5NPCSZX"),
    ],
)
def test_service_https_urls(validator, url):
    assert validator(url) == url


@pytest.mark.parametrize(
    "url",
    [
        "http://www.disneyplus.com/video/id",
        "https://www.disneyplus.com.evil.test/video/id",
        "https://www.disneyplus.com@evil.test/video/id",
        "https://user:password@www.disneyplus.com/video/id",
        "https://www.disneyplus.com:444/video/id",
        "https://www.disneyplus.com:bad/video/id",
        "https://www.disneyplus.com/",
        "https://www.disneyplus.com/video/one two",
        "https://www.disneyplus.com/video/one\ntwo",
        "https://[broken/video/id",
        "//www.disneyplus.com/video/id",
    ],
)
def test_invalid_urls(url):
    with pytest.raises(vol.Invalid):
        disney_video(url)


def test_url_scheme_is_normalized_without_changing_title_path():
    assert disney_video("HTTPS://WWW.DISNEYPLUS.COM/video/TitleID") == (
        "https://WWW.DISNEYPLUS.COM/video/TitleID"
    )


def test_asin_rejects_non_ascii_casefold_characters():
    with pytest.raises(vol.Invalid):
        prime_video("B0B5NPCSKX")
