#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys

_CURRENT_FOCUS_RE = re.compile(r"mCurrentFocus=Window\{[^}]*\s(?P<pkg>[a-zA-Z0-9_.]+)/(?P<activity>[^\s}]+)")
_FOCUSED_APP_RE = re.compile(r"mFocusedApp=AppWindowToken\{[^}]*\s(?P<pkg>[a-zA-Z0-9_.]+)/(?P<activity>[^\s}]+)")


def adb_shell(cmd: str, timeout_s: int = 15) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT, timeout=timeout_s)
    return out


def main() -> int:
    try:
        dump = adb_shell("dumpsys window windows", timeout_s=20)
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        return 1
    except subprocess.TimeoutExpired:
        print("Timed out running dumpsys window windows")
        return 1

    focus_pkg = None
    focus_act = None

    for line in dump.splitlines():
        m = _CURRENT_FOCUS_RE.search(line)
        if m:
            focus_pkg = m.group("pkg")
            focus_act = m.group("activity")
            break

    if not focus_pkg:
        for line in dump.splitlines():
            m = _FOCUSED_APP_RE.search(line)
            if m:
                focus_pkg = m.group("pkg")
                focus_act = m.group("activity")
                break

    if not focus_pkg:
        print("No focused window/app found")
        return 2

    print("Focused window/app:")
    print(f"  package: {focus_pkg}")
    print(f"  activity: {focus_act}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
