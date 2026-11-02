from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from adb_shell.adb_device import AdbDeviceTcp
from adb_shell.auth.keygen import keygen
from adb_shell.auth.sign_pythonrsa import PythonRSASigner

from .const import ANDROIDTV_STORAGE_KEY, OUR_STORAGE_KEY

_LOGGER = logging.getLogger(__name__)


class ADBConnectionError(RuntimeError):
    pass


class ADBAuthError(RuntimeError):
    pass


@dataclass(frozen=True)
class AdbKeys:
    private_key: Path
    public_key: Path


class AdbAppStateClient:
    def __init__(
        self,
        hass: Any,
        host: str,
        port: int,
        adbkey_path: str | None,
        reuse_androidtv_key: bool,
    ) -> None:
        self._hass = hass
        self._host = host
        self._port = port
        self._adbkey_path = adbkey_path
        self._reuse_androidtv_key = reuse_androidtv_key

        self._device: AdbDeviceTcp | None = None
        self._signer: PythonRSASigner | None = None

    def _config_path(self, rel: str) -> Path:
        return (Path(self._hass.config.config_dir) / rel).resolve()

    def _resolve_keys(self) -> AdbKeys:
        # 1) Explicit key path (relative to HA config dir)
        if self._adbkey_path:
            priv = self._config_path(self._adbkey_path)
            pub = (
                priv.with_suffix(priv.suffix + ".pub")
                if priv.suffix
                else Path(str(priv) + ".pub")
            )
            if not priv.exists() or not pub.exists():
                raise ADBAuthError(f"ADB key not found: {priv} / {pub}")
            return AdbKeys(private_key=priv, public_key=pub)

        # 2) Reuse AndroidTV integration key if present
        if self._reuse_androidtv_key:
            priv = self._config_path(ANDROIDTV_STORAGE_KEY)
            pub = self._config_path(ANDROIDTV_STORAGE_KEY + ".pub")
            if priv.exists() and pub.exists():
                return AdbKeys(private_key=priv, public_key=pub)

        # 3) Generate / reuse our own key in .storage
        priv = self._config_path(OUR_STORAGE_KEY)
        pub = self._config_path(OUR_STORAGE_KEY + ".pub")
        if not (priv.exists() and pub.exists()):
            priv.parent.mkdir(parents=True, exist_ok=True)
            keygen(str(priv))
        return AdbKeys(private_key=priv, public_key=pub)

    def _get_signer(self) -> PythonRSASigner:
        if self._signer is not None:
            return self._signer

        keys = self._resolve_keys()
        priv_bytes = keys.private_key.read_bytes()
        pub_bytes = keys.public_key.read_bytes()
        self._signer = PythonRSASigner(pub_bytes, priv_bytes)
        return self._signer

    def connect(self) -> None:
        self._device = AdbDeviceTcp(
            self._host, self._port, default_transport_timeout_s=8.0
        )
        signer = self._get_signer()
        try:
            self._device.connect(rsa_keys=[signer], auth_timeout_s=10.0)
        except Exception as exc:  # noqa: BLE001
            msg = str(exc)
            if "AUTH" in msg.upper() or "not authorized" in msg.lower():
                raise ADBAuthError(msg) from exc
            raise ADBConnectionError(msg) from exc

    def close(self) -> None:
        if self._device is None:
            return
        try:
            self._device.close()
        except Exception:  # noqa: BLE001
            pass
        self._device = None

    def shell(self, command: str, timeout_s: float = 6.0) -> str:
        if self._device is None:
            self.connect()
        assert self._device is not None
        try:
            out = self._device.shell(command, timeout_s=timeout_s)
        except Exception as exc:  # noqa: BLE001
            raise ADBConnectionError(str(exc)) from exc
        if out is None:
            text = ""
        elif isinstance(out, (bytes, bytearray, memoryview)):
            text = bytes(out).decode("utf-8", errors="replace")
        elif isinstance(out, str):
            text = out
        else:
            text = str(out)

        return text.strip()
