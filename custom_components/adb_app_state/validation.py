"""Shared validation for configuration, action data and Android deep links."""

import ipaddress
import re
from urllib.parse import urlsplit

import probatio as vol

_DISNEY_ID = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE | re.ASCII,
)
_ASIN = re.compile(r"[A-Z0-9]{10}", re.IGNORECASE | re.ASCII)
_HOST_LABEL = re.compile(
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", re.IGNORECASE | re.ASCII
)
_PRIME_DOMAINS = (
    "primevideo.com",
    "amazon.de",
    "amazon.com",
    "amazon.co.uk",
    "amazon.fr",
    "amazon.it",
    "amazon.es",
    "amazon.co.jp",
    "amazon.in",
    "amazon.com.au",
    "amazon.com.br",
    "amazon.ca",
    "amazon.com.mx",
    "amazon.nl",
    "amazon.se",
    "amazon.pl",
    "amazon.com.be",
    "amazon.com.tr",
    "amazon.co.za",
)


def integer(value: object) -> int:
    """Reject booleans and fractional numbers instead of silently truncating."""
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and re.fullmatch(r"[+-]?[0-9]+", value):
        return int(value)
    raise vol.Invalid("Expected an integer")


PORT = vol.All(integer, vol.Range(min=1, max=65535))
SCAN_INTERVAL = vol.All(integer, vol.Range(min=1))
PROFILE_INDEX = vol.All(integer, vol.Range(min=0, max=10))
TIMEOUT = vol.All(integer, vol.Range(min=10, max=600))
REPEAT_COUNT = vol.All(integer, vol.Range(min=1, max=200))
DELAY_MS = vol.All(integer, vol.Range(min=0, max=2000))


def host(value: str) -> str:
    if not isinstance(value, str) or not (value := value.strip()):
        raise vol.Invalid("Expected an IP address or hostname")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        labels = value.removesuffix(".").split(".")
        if (
            len(value) > 253
            or re.fullmatch(r"[0-9.]+", value)
            or not all(_HOST_LABEL.fullmatch(label) for label in labels)
        ):
            raise vol.Invalid("Expected an IP address or hostname") from None
    return value


def pin(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]+", value):
        raise vol.Invalid("PIN must contain ASCII digits only")
    return value


def _video(value: str, pattern: re.Pattern[str], domains: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not (value := value.strip()):
        raise vol.Invalid("Expected a video ID or an HTTPS video URL")
    if pattern.fullmatch(value):
        return value
    if len(value) > 2048 or any(ord(char) <= 32 or ord(char) == 127 for char in value):
        raise vol.Invalid("Invalid video URL")
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname or ""
        valid = (
            parsed.scheme == "https"
            and parsed.username is None
            and parsed.password is None
            and parsed.port in (None, 443)
            and parsed.path not in ("", "/")
            and any(
                hostname == domain or hostname.endswith("." + domain)
                for domain in domains
            )
        )
    except ValueError as exc:
        raise vol.Invalid("Invalid video URL") from exc
    if not valid:
        raise vol.Invalid(
            "Expected a valid ID or an HTTPS URL for the selected service"
        )
    return parsed._replace(scheme="https").geturl()


def disney_video(value: str) -> str:
    return _video(value, _DISNEY_ID, ("disneyplus.com",))


def prime_video(value: str) -> str:
    value = _video(value, _ASIN, _PRIME_DOMAINS)
    return value.upper() if _ASIN.fullmatch(value) else value
