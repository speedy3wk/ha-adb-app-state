# ADB technique checks

Small scripts to validate ADB data extraction directly against your TV.

## Requirements
- `adb` in PATH
- Target device already connected (e.g. `adb connect <ip>:<port>`)

## Scripts

### 1) Media session playback state

```
python3 tools/adb_tests/media_session_check.py
```

Outputs the parsed active media session state (package + PlaybackState fields).

### 2) Foreground activity

```
python3 tools/adb_tests/activity_check.py
```

Outputs the foreground package/activity parsed from `dumpsys activity activities`.

### 3) View dump (Disney+ markers)

```
python3 tools/adb_tests/view_dump_check.py
```

Downloads the visible-window-views ZIP via ADB, parses visible components and Disney+ markers.

### 3b) View dump resource-ids (raw)

```
python3 tools/adb_tests/view_dump_ids_check.py
```

Extracts raw resource-ids from the view dump ZIP (useful for Prime profile markers).

### 4) UIAutomator dump (XML)

```
python3 tools/adb_tests/uiautomator_check.py
```

Fetches a live UIAutomator XML dump and lists packages and resource-ids. Useful when
view dumps are redacted during DRM playback.

### 5) Window focus (dumpsys window windows)

```
python3 tools/adb_tests/window_windows_check.py
```

Parses focused window/app from `dumpsys window windows`.

### 6) SurfaceFlinger layers

```
python3 tools/adb_tests/surfaceflinger_check.py
```

Lists compositor layers (may reveal active app surfaces when UI is redacted).

### 6b) SurfaceFlinger full dump (Prime blocks)

```
python3 tools/adb_tests/surfaceflinger_full_check.py
```

Parses full SurfaceFlinger dump and extracts Prime SurfaceView blocks (includes Comp Type and Frame Rate).

### 7) SurfaceFlinger heuristic tester (Prime)

```
python3 tools/adb_tests/surfaceflinger_heuristic_test.py
```

Continuously parses the SurfaceFlinger HWC section and infers MOVIE/DETAIL/IN_APP from
frame-rate + display frame. Use `--interval 4` for 4s polling.

### Run all

```
./tools/adb_tests/run_all.sh
```
