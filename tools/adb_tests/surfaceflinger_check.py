#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys


def adb_shell(cmd: str, timeout_s: int = 20) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT, timeout=timeout_s)
    return out


def main() -> int:
    try:
        dump = adb_shell("dumpsys SurfaceFlinger --list", timeout_s=25)
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        return 1
    except subprocess.TimeoutExpired:
        print("Timed out running dumpsys SurfaceFlinger")
        return 1

    layers = [line.strip() for line in dump.splitlines() if line.strip()]
    print(f"SurfaceFlinger layers: {len(layers)}")
    for layer in layers[:40]:
        print(f"  {layer}")
    if len(layers) > 40:
        print(f"  ... (+{len(layers) - 40} more)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
