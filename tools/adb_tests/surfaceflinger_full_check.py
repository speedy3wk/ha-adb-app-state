#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import sys

_LAYER_BLOCK_RE = re.compile(r"SurfaceView.*(amazonvideo|ignition)", re.IGNORECASE)


def adb_shell(cmd: str, timeout_s: int = 25) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT, timeout=timeout_s)
    return out


def extract_prime_layers(dumpsys_text: str) -> list[str]:
    lines = dumpsys_text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _LAYER_BLOCK_RE.match(line):
            block = [line.strip()]
            # include next 1-2 lines if they look like data rows
            if i + 1 < len(lines):
                block.append(lines[i + 1].strip())
            if i + 2 < len(lines) and lines[i + 2].strip().startswith("rel"):
                block.append(lines[i + 2].strip())
            out.append("\n".join(block))
        i += 1
    return out


def main() -> int:
    try:
        dump = adb_shell("dumpsys SurfaceFlinger", timeout_s=30)
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        return 1
    except subprocess.TimeoutExpired:
        print("Timed out running dumpsys SurfaceFlinger")
        return 1

    layers = extract_prime_layers(dump)
    if not layers:
        print("No Prime SurfaceView layers found in SurfaceFlinger dump")
        return 2

    print("Prime SurfaceFlinger layer blocks:")
    for block in layers:
        print("-")
        print(block)

    return 0


if __name__ == "__main__":
    sys.exit(main())
