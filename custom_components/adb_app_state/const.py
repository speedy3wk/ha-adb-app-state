from __future__ import annotations

DOMAIN = "adb_app_state"
PLATFORMS: list[str] = ["sensor", "binary_sensor"]

CONF_HOST = "host"
CONF_PORT = "port"
CONF_NAME = "name"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_REUSE_ANDROIDTV_KEY = "reuse_androidtv_key"
CONF_ADBKEY_PATH = "adbkey_path"

DEFAULT_PORT = 5555
DEFAULT_SCAN_INTERVAL = 5
DEFAULT_REUSE_ANDROIDTV_KEY = True

# UI states (generic)
UI_STATE_NOT_SUPPORTED = "NOT_SUPPORTED"
UI_STATE_OFF = "OFF"
UI_STATE_IN_APP = "IN_APP"
UI_STATE_CHOOSE_PROFILE = "CHOOSE_PROFILE"
UI_STATE_ENTER_PIN = "ENTER_PIN"
UI_STATE_HOME = "HOME"
UI_STATE_PREVIEW = "PREVIEW"
UI_STATE_MOVIE_DETAIL = "MOVIE_DETAIL"
UI_STATE_MOVIE = "MOVIE"

# Key locations (relative to HA config dir)
ANDROIDTV_STORAGE_KEY = ".storage/androidtv_adbkey"
OUR_STORAGE_KEY = ".storage/adb_app_state_adbkey"
