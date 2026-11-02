# ADB App State

<img src="custom_components/adb_app_state/brand/logo.png" alt="ADB App State logo" width="320">

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://www.hacs.xyz/docs/faq/custom_repositories/)
[![Release](https://img.shields.io/github/v/release/speedy3wk/ha-adb-app-state.svg)](https://github.com/speedy3wk/ha-adb-app-state/releases)
[![Validate](https://github.com/speedy3wk/ha-adb-app-state/actions/workflows/validate.yml/badge.svg)](https://github.com/speedy3wk/ha-adb-app-state/actions/workflows/validate.yml)
[![Tests](https://github.com/speedy3wk/ha-adb-app-state/actions/workflows/tests.yml/badge.svg)](https://github.com/speedy3wk/ha-adb-app-state/actions/workflows/tests.yml)
[![Built with AI](https://img.shields.io/badge/Built%20with-AI-blue.svg)](https://github.com/features/copilot)

Detect Disney+ and Prime Video screens on Android TV from Home Assistant over ADB. Created with AI.

Requires Home Assistant **2026.10.4 or newer**. This is an early, best-effort integration: app updates and device firmware can change detection behavior. It is not affiliated with Disney, Amazon or Google.

## Highlights

- UI state sensor and an **Input required** binary sensor.
- Disney+ detection for profile selection, PIN entry, home, title details and the playback screen.
- Prime Video detection for in-app screens, previews and movies using SurfaceFlinger hints.
- Actions to open a title, handle selected prompts and optionally pause when playback is detected.
- Media session controls for play, pause, stop, next and previous.
- Local polling, configurable ADB keys and English/German configuration UI. No external API or cloud account credentials are used by this integration; the streaming apps still need their own accounts and internet access.

## Requirements

- An Android TV device reachable from Home Assistant over TCP ADB (typically port `5555`).
- Network debugging enabled and the ADB authorization prompt accepted on the TV.
- Disney+ and/or the Android TV version of Prime Video installed and already signed in.
- A device exposing `dumpsys activity activities`, `cmd window dump-visible-window-views` and, for Prime Video, `dumpsys SurfaceFlinger`.

Detection is based on Android TV/Shield-style output, not a universal Android or Fire TV compatibility guarantee. Pairing-code-based wireless debugging is not implemented. Keep ADB on a trusted local network; never expose its port to the internet.

## Installation

### HACS

This is a **custom repository**, not currently part of the HACS default list.

[![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=speedy3wk&repository=ha-adb-app-state&category=integration)

1. In HACS, open **Custom repositories**.
2. Add `https://github.com/speedy3wk/ha-adb-app-state` with category **Integration**.
3. Download **ADB App State** and restart Home Assistant.
4. Open **Settings > Devices & services > Add integration** and search for **ADB App State**.

### Manual

Copy [`custom_components/adb_app_state`](./custom_components/adb_app_state) into your Home Assistant `config/custom_components/` directory, restart Home Assistant, then add **ADB App State**.

## Configuration

Enter a device name, host/IP address and ADB port (default `5555`). Accept the authorization prompt on the TV during setup.

Under **Configure**, you can change:

| Option | Default | Description |
|---|---|---|
| Polling interval | 5 seconds | Time between status updates. A poll can take longer if the device is slow. Use a positive value. |
| Reuse AndroidTV key | Enabled | Reuse `.storage/androidtv_adbkey` and its `.pub` file when available. |
| ADB private key path | Empty | Optional key path relative to the HA configuration directory; the matching `.pub` file must exist. |

Otherwise, the integration generates its own key pair in `.storage/adb_app_state_adbkey`. Initial setup uses automatic key selection; an explicit key path can only be configured after setup. More than one device can be added.

## Entities

| Entity | Purpose |
|---|---|
| **UI state** sensor | Current recognized screen; attributes include `input_required` and `foreground_app` when detectable. |
| **Input required** binary sensor | On when Disney+ shows a profile picker, PIN prompt or detected error dialog. Prime Video does not currently detect these prompts. |

### UI states

| State | Meaning |
|---|---|
| `OFF` | ADB is unreachable/timed out, or fallback dumps are empty. This does **not** prove the TV is powered off. |
| `NOT_SUPPORTED` | The foreground app is unsupported or could not be determined. |
| `IN_APP` | A supported app is open but its screen is not recognized. Also used for detected Disney+ error dialogs, with `input_required: true`. |
| `CHOOSE_PROFILE` | Disney+ profile picker. |
| `ENTER_PIN` | Disney+ PIN entry. |
| `HOME` | Disney+ home screen. |
| `MOVIE_DETAIL` | Disney+ title details. |
| `PREVIEW` | Prime Video preview heuristic. |
| `MOVIE` | Disney+ playback screen or Prime Video movie heuristic. Paused playback may still have this state. |

These are **screen states**, not an exact playing/paused media status. No media player entity or title metadata is provided.

## Actions

All actions accept an optional `entry_id`. It is required when multiple devices are configured. This is the integration's config entry ID, not an entity ID.

### Prepare a Disney+ movie

```yaml
action: adb_app_state.prepare_disney_movie
data:
  film_id: YOUR_DISNEY_VIDEO_UUID
  profile_index: 0
  pause_on_start: true
  timeout: 90
```

- `film_id` is a playable Disney+ video UUID or full Disney+ URL. UUIDs use `https://www.disneyplus.com/de-de/play/<film_id>`.
- `profile_index` is optional and zero-based; it moves right from the currently focused profile, not from a verified absolute position.
- Optional `pin` sends digits to a detected PIN screen. Avoid storing real PINs in public examples or shared traces.
- `pause_on_start` defaults to `false`; `timeout` defaults to 90 seconds.
- The action can retry deep links, restart the app's task and press the focused play button. A detected Disney+ error dialog is dismissed and reported as an error.

### Prepare a Prime Video movie

```yaml
action: adb_app_state.prepare_prime_movie
data:
  film_asin: YOUR_AMAZON_ASIN
  auto_login: true
  pause_on_start: true
  timeout: 90
```

`film_asin` also accepts a full URL; ASINs use `https://watch.amazon.de/watch?asin=<ASIN>`. `auto_login` defaults to `true` and sends **one** DPAD-center press on an `IN_APP` screen. It does not enter account credentials or verify the focused control. `pause_on_start` defaults to `false`.

Both preparation actions are best-effort navigation, not a guarantee that the requested title started. Existing subscriptions, availability, app focus, age restrictions and UI changes affect the result. The timeout is a loop deadline, not a strict upper bound on the runtime of an in-flight ADB command. Avoid running preparation actions concurrently for the same device.

### Dispatch a media key

```yaml
action: adb_app_state.media_dispatch
data:
  key: play-pause
  times: 1
  delay_ms: 250
```

Supported keys: `play`, `pause`, `play-pause`, `stop`, `next`, `previous`, `headsethook`, `mute`. Commands go to Android's active media session, not a selected app. Repeats are clamped to 1-200; the default delay is 250 ms.

**Fast-forward and rewind are intentionally disabled** because they can disrupt the Disney+ media session on the original target device.

## Troubleshooting

- **Cannot connect:** check the host, TCP ADB port, network debugging and the TV's authorization prompt. Setup needs a reachable device.
- **Authentication failure:** authorize the Home Assistant key or verify the selected private/public key pair. ADB keys are credentials; never upload them.
- **Unexpected state:** app resource IDs and compositor output differ between versions. `IN_APP` and `NOT_SUPPORTED` are expected fallbacks.
- **Prime preview mistaken for a movie:** detection uses protected layers, geometry and frame-rate hints, including a 1920x1080 full-frame heuristic. Other resolutions and firmware can need adjustments.
- **Slow updates:** Prime Video's SurfaceFlinger dump can take up to 30 seconds. Reducing the polling interval does not make the device respond faster.
- **Navigation fails:** first verify that the deep link works on your device/account and that the correct app is signed in.

The optional [ADB technique checks](./tools/adb_tests/README.md) help investigate device output. They require a separate `adb` CLI and an authorized device; automated tests do not connect to a real TV. Raw dumps may contain personal data and are intentionally excluded from Git.

## Development

Like the other integrations in this account, CI runs Hassfest and HACS validation plus lint, formatting, type checks and tests against a pinned stable Home Assistant runtime.

```sh
python3.14 -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
ruff check custom_components tests
ruff format --check custom_components tests
pyright --pythonpath "$(command -v python)"
python -m pytest -q
```

Tests use synthetic ADB output and mocked connections. Passing tests do not certify playback or compatibility with physical devices. Do not point automated tests at your Home Assistant installation.

### HACS listing readiness

The repository includes a root README, MIT license, HACS metadata, release version, maintainer/issue links, validation workflows and local PNG brand assets. Artwork sources are in [`docs/assets`](./docs/assets); Home Assistant loads images from [`brand`](./custom_components/adb_app_state/brand).

A future default-list submission is a separate step, subject to the [current HACS inclusion requirements](https://www.hacs.xyz/docs/publish/include/) and maintainer review. No HACS listing or acceptance is implied by this release.

## License

This project, including its original TV/ADB artwork, is distributed under the MIT License. See [LICENSE](./LICENSE).
