#!/usr/bin/env python3
from __future__ import annotations

import base64
import subprocess
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
VIEW_DUMP_PATH = PROJECT_ROOT / "custom_components" / "adb_app_state" / "view_dump.py"

spec = importlib.util.spec_from_file_location("view_dump", VIEW_DUMP_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Unable to load {VIEW_DUMP_PATH}")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

parse_primary_package_from_window_views_zip = module.parse_primary_package_from_window_views_zip
parse_visible_components_from_window_views_zip = module.parse_visible_components_from_window_views_zip


def adb_shell(cmd: str, timeout_s: int = 15) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT, timeout=timeout_s)
    return out


def main() -> int:
    try:
        view_b64 = adb_shell("cmd window dump-visible-window-views | base64", timeout_s=20)
    except subprocess.CalledProcessError as exc:
        print(exc.output)
        return 1
    except subprocess.TimeoutExpired:
        print("Timed out running view dump")
        return 1

    zip_bytes = base64.b64decode(view_b64)
    print(f"window_views_zip_len: {len(zip_bytes)}")

    ignore_pkgs = {
        "android",
        "com.android.systemui",
        "com.android.settings",
        "com.google.android.gms",
        "com.google.android.inputmethod.latin",
    }
    foreground_app = parse_primary_package_from_window_views_zip(zip_bytes, ignore_packages=ignore_pkgs)
    print(f"foreground_app: {foreground_app}")

    visible_components = parse_visible_components_from_window_views_zip(zip_bytes)
    print("visible_components:")
    for comp in visible_components[:20]:
        print(f"  - {comp}")
    if len(visible_components) > 20:
        print(f"  ... (+{len(visible_components) - 20} more)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
