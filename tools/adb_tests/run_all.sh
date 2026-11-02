#!/usr/bin/env bash
set -euo pipefail

python3 tools/adb_tests/activity_check.py
python3 tools/adb_tests/media_session_check.py
python3 tools/adb_tests/view_dump_check.py
python3 tools/adb_tests/view_dump_ids_check.py
python3 tools/adb_tests/uiautomator_check.py
python3 tools/adb_tests/window_windows_check.py
python3 tools/adb_tests/surfaceflinger_check.py
python3 tools/adb_tests/surfaceflinger_full_check.py
