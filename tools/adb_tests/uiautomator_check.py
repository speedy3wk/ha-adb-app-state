#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys

_UIA_PKG_RE = re.compile(r"package=\"([a-zA-Z0-9_.]+)\"")
_UIA_RES_ID_RE = re.compile(r"resource-id=\"([a-zA-Z0-9_.:]+)\"")


def adb_shell(cmd: str, timeout_s: int = 20) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT, timeout=timeout_s)
    return out


def main() -> int:
    try:
        xml = adb_shell("uiautomator dump /dev/tty", timeout_s=25)
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        return 1
    except subprocess.TimeoutExpired:
        print("Timed out running uiautomator dump")
        return 1

    pkg_counts: dict[str, int] = {}
    for pkg in _UIA_PKG_RE.findall(xml):
        pkg_counts[pkg] = pkg_counts.get(pkg, 0) + 1

    res_ids = _UIA_RES_ID_RE.findall(xml)

    print("uiautomator packages:")
    for pkg, count in sorted(pkg_counts.items(), key=lambda kv: kv[1], reverse=True)[:10]:
        print(f"  {pkg}: {count}")

    print("resource-ids (sample):")
    for rid in res_ids[:30]:
        print(f"  {rid}")
    if len(res_ids) > 30:
        print(f"  ... (+{len(res_ids) - 30} more)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
