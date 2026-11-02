#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PRIME_PKG = "com.amazon.amazonvideo.livingroom"

HWC_SECTION_START_RE = re.compile(r"Display\s+0\s+HWC\s+layers:", re.IGNORECASE)
HWC_SECTION_END_RE = re.compile(r"h/w\s+composer\s+state:", re.IGNORECASE)

FPS_RE = re.compile(r"(?P<fps>[0-9.]+fps\s+[^\[]+)")

DEFAULT_LOG = Path(__file__).with_suffix(".log")


def adb_shell(cmd: str, timeout_s: int = 30) -> str:
    out = subprocess.check_output(["adb", "shell", cmd], text=True, stderr=subprocess.STDOUT, timeout=timeout_s)
    return out


def extract_hwc_section(text: str) -> str:
    start_m = HWC_SECTION_START_RE.search(text)
    if not start_m:
        return ""
    end_m = HWC_SECTION_END_RE.search(text, start_m.end())
    end = end_m.start() if end_m else len(text)
    return text[start_m.start() : end]


def parse_prime_state(hwc_text: str) -> tuple[str, dict[str, str]]:
    """Return (state, debug) based on HWC layers section.

    Heuristic:
    - If SurfaceView #1 has frame rate and full frame (0,0,1920,1080) => MOVIE
    - If SurfaceView #1 has frame rate and cropped frame => DETAIL
    - Otherwise IN_APP
    """
    debug: dict[str, str] = {}
    lines = hwc_text.splitlines()
    for i, line in enumerate(lines):
        if "SurfaceView" not in line:
            continue
        if "amazon.amazonvideo" not in line:
            continue

        idx_match = re.search(r"#(\d+)", line)
        if not idx_match:
            continue
        idx = idx_match.group(1)
        debug["layer_idx"] = idx

        if idx != "1":
            continue

        if i + 1 >= len(lines):
            continue
        row = lines[i + 1]
        if "|" not in row:
            continue
        parts = [p.strip() for p in row.split("|")]
        disp_l = disp_t = disp_r = disp_b = -1
        for segment in parts:
            nums = segment.split()
            if len(nums) >= 4 and all(n.isdigit() for n in nums[:4]):
                disp_l, disp_t, disp_r, disp_b = map(int, nums[:4])
                debug["disp_frame"] = f"{disp_l},{disp_t},{disp_r},{disp_b}"
                break

        fr_match = FPS_RE.search(row)
        fr = (fr_match.group("fps") if fr_match else "").strip()
        debug["frame_rate"] = fr or "none"

        has_frame_rate = bool(fr)
        full_frame = disp_l == 0 and disp_t == 0 and disp_r == 1920 and disp_b == 1080
        # Scan following lines for extra hints (protected content, layer bounds, translate)
        protected = False
        translate = False
        bounds_h = None
        for j in range(i + 1, min(i + 40, len(lines))):
            l2 = lines[j]
            if j != i + 1 and "SurfaceView" in l2 and "amazon.amazonvideo" in l2:
                break
            if "hasProtectedContent=true" in l2:
                protected = True
            if "TRANSLATE" in l2:
                translate = True
            if "geomLayerBounds=" in l2:
                m = re.search(r"geomLayerBounds=\[[0-9.]+\s+[0-9.]+\s+[0-9.]+\s+(?P<h>[0-9.]+)\]", l2)
                if m:
                    try:
                        bounds_h = float(m.group("h"))
                    except ValueError:
                        pass

        debug["protected"] = str(protected)
        if bounds_h is not None:
            debug["bounds_h"] = str(int(bounds_h))
        debug["translate"] = str(translate)

        if protected:
            return "MOVIE", debug
        if translate or (bounds_h is not None and bounds_h < 900):
            return "DETAIL", debug
        if has_frame_rate:
            if full_frame:
                return "MOVIE", debug
            return "DETAIL", debug

    return "IN_APP", debug


def loop(interval_s: float, log_path: Path) -> None:
    while True:
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            dump = adb_shell("dumpsys SurfaceFlinger", timeout_s=30)
            hwc = extract_hwc_section(dump)
            state, dbg = parse_prime_state(hwc)
            line = f"{ts} state={state} frame_rate={dbg.get('frame_rate','')} disp={dbg.get('disp_frame','')}"
        except subprocess.CalledProcessError as exc:
            line = f"{ts} ERROR adb: {exc.output.strip()}"
        except Exception as exc:  # noqa: BLE001
            line = f"{ts} ERROR: {exc}"

        log_path.write_text(log_path.read_text(encoding="utf-8") + line + "\n" if log_path.exists() else line + "\n", encoding="utf-8")
        print(line)
        time.sleep(interval_s)


def main() -> int:
    parser = argparse.ArgumentParser(description="SurfaceFlinger heuristic tester (Prime)")
    parser.add_argument("--interval", type=float, default=4.0, help="Polling interval in seconds")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG, help="Log file path")
    args = parser.parse_args()

    print(f"Logging to: {args.log}")
    try:
        loop(args.interval, args.log)
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
