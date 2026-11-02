#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys
from typing import Any

_MEDIA_SESSION_PACKAGE_RE = re.compile(r"package=(?P<pkg>[a-z0-9_.]+)", re.IGNORECASE)
_MEDIA_SESSION_PLAYBACK_RE = re.compile(r"PlaybackState\s*\{(?P<body>[^}]*)\}", re.IGNORECASE)
_MEDIA_SESSION_STATE_RE = re.compile(r"state=(?P<state>\d+)")
_MEDIA_SESSION_POS_RE = re.compile(r"position=(?P<pos>\d+)")
_MEDIA_SESSION_SPEED_RE = re.compile(r"speed=(?P<speed>[0-9.]+)")
_MEDIA_SESSION_UPDATED_RE = re.compile(r"updated=(?P<updated>\d+)")


def adb_shell(cmd: str) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT)
    return out


def parse_media_session_dump(dumpsys_text: str) -> dict[str, Any] | None:
    if not dumpsys_text:
        return None

    sessions: list[dict[str, Any]] = []
    current: list[str] = []
    for line in dumpsys_text.splitlines():
        if line.strip().startswith("Session #"):
            if current:
                sessions.append({"raw": "\n".join(current)})
                current = []
        current.append(line)
    if current:
        sessions.append({"raw": "\n".join(current)})

    parsed: list[dict[str, Any]] = []
    for sess in sessions:
        raw = sess.get("raw") or ""
        pkg_m = _MEDIA_SESSION_PACKAGE_RE.search(raw)
        playback_m = _MEDIA_SESSION_PLAYBACK_RE.search(raw)
        if not pkg_m or not playback_m:
            continue

        body = playback_m.group("body")
        state_m = _MEDIA_SESSION_STATE_RE.search(body)
        if not state_m:
            continue

        entry: dict[str, Any] = {
            "package": pkg_m.group("pkg").lower(),
            "state": int(state_m.group("state")),
            "active": "mActive=true" in raw or "isActive=true" in raw or "active=true" in raw,
        }

        pos_m = _MEDIA_SESSION_POS_RE.search(body)
        if pos_m:
            entry["position_ms"] = int(pos_m.group("pos"))
        speed_m = _MEDIA_SESSION_SPEED_RE.search(body)
        if speed_m:
            entry["speed"] = float(speed_m.group("speed"))
        updated_m = _MEDIA_SESSION_UPDATED_RE.search(body)
        if updated_m:
            entry["updated_ms"] = int(updated_m.group("updated"))

        parsed.append(entry)

    if not parsed:
        return None

    def _rank(item: dict[str, Any]) -> tuple[int, int]:
        active = 1 if item.get("active") else 0
        state = item.get("state")
        playing = 1 if state == 3 else 0
        paused = 1 if state == 2 else 0
        return (active, playing or paused)

    best = sorted(parsed, key=_rank, reverse=True)[0]
    return best


def main() -> int:
    try:
        dump = adb_shell("dumpsys media_session")
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        return 1

    parsed = parse_media_session_dump(dump)
    if not parsed:
        print("No PlaybackState found in dumpsys media_session")
        return 2

    print("Parsed media session:")
    for k, v in parsed.items():
        print(f"  {k}: {v}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
