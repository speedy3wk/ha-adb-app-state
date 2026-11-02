#!/usr/bin/env python3
from __future__ import annotations

import base64
import re
import subprocess
import sys
from collections import Counter

_ID_RE = re.compile(rb"([a-zA-Z0-9_.]{3,200}):id/([a-zA-Z0-9_]{2,200})")


def adb_shell(cmd: str, timeout_s: int = 20) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT, timeout=timeout_s)
    return out


def main() -> int:
    try:
        view_b64 = adb_shell("cmd window dump-visible-window-views | base64", timeout_s=25)
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        return 1
    except subprocess.TimeoutExpired:
        print("Timed out running view dump")
        return 1

    zip_bytes = base64.b64decode(view_b64)
    if not zip_bytes:
        print("Empty view dump")
        return 2

    try:
        import io
        import zipfile

        counts: Counter[str] = Counter()
        with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
            for name in zf.namelist():
                if name.endswith("/"):
                    continue
                data = zf.read(name)
                for m in _ID_RE.finditer(data):
                    pkg = m.group(1).decode("utf-8", errors="ignore")
                    rid = m.group(2).decode("utf-8", errors="ignore")
                    counts[f"{pkg}:id/{rid}"] += 1

        print(f"resource-ids found: {len(counts)}")
        for rid, cnt in counts.most_common(50):
            print(f"  {cnt:>4}  {rid}")
        if len(counts) > 50:
            print(f"  ... (+{len(counts) - 50} more)")
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to parse view dump: {exc}")
        return 3

    return 0


if __name__ == "__main__":
    sys.exit(main())
