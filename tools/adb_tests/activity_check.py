#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys

_RESUMED_ACTIVITY_RE = re.compile(
    r"mResumedActivity:.*?\s(?P<pkg>[a-zA-Z0-9_.]+)/(?P<activity>[^\s}]+)", re.IGNORECASE
)
_FOCUSED_ACTIVITY_RE = re.compile(
    r"mFocusedActivity:.*?\s(?P<pkg>[a-zA-Z0-9_.]+)/(?P<activity>[^\s}]+)", re.IGNORECASE
)


def adb_shell(cmd: str) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT)
    return out


def parse_top_activity(dumpsys_text: str) -> tuple[str | None, str | None]:
    for line in (dumpsys_text or "").splitlines():
        m = _RESUMED_ACTIVITY_RE.search(line)
        if m:
            return m.group("pkg"), m.group("activity")
    for line in (dumpsys_text or "").splitlines():
        m = _FOCUSED_ACTIVITY_RE.search(line)
        if m:
            return m.group("pkg"), m.group("activity")
    return None, None


def main() -> int:
    try:
        dump = adb_shell("dumpsys activity activities")
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        return 1

    pkg, activity = parse_top_activity(dump)
    if not pkg:
        print("No foreground activity found in dumpsys activity")
        return 2

    print("Foreground activity:")
    print(f"  package: {pkg}")
    print(f"  activity: {activity}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
