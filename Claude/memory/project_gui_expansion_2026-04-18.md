# GUI expansion — shipped 2026-04-18 (not yet on Jetson)

Large extension of the browser dashboard on branch `auto-nav-test`. Verified against the local mock server only; no real-hardware testing yet.

## Layout
Three tabs: **Dashboard**, **Telemetry**, **Manual**. Map + video live *above* the tab bar so they're visible in every tab. Header carries E-Stop, Mute, Admin buttons + the link-quality strip.

- **Dashboard**: four columns — Camera Controls / Status / Mission Control (pre-arm + phase + basic planning + dynamic action buttons) / Advanced Planning (geofence, survey/lawnmower, mission templates).
- **Telemetry**: read-only grid (Flight / Mission / Position / Servos / Battery / EKF / Link / Sensors) + rolling 10-row log table at the bottom.
- **Manual**: admin-gated. Virtual sliders + Gamepad API; sends `manual_rc` at 20 Hz while engaged; auto-releases on navigation.

## Safety layer
- Jetson watchdog that fires configurable failsafe (HOLD / RTL / DISARM, default HOLD) if the browser stops sending `gcs_heartbeat` for >8 s while armed. Latches; resets when link returns.
- Always-visible E-Stop (no confirmation, by design).
- Pre-arm checklist disables `START MISSION` unless all rows green; admin can bypass.
- Web Audio beeps on failsafe / low battery / link loss / E-Stop, with a header mute toggle.
- Client-side fence breach check as a belt on top of the Pixhawk-side fence action.

## Admin auth
`AQUABOT_ADMIN_PW` env var at service startup → SHA-256 hash + in-memory session tokens. Admin gates `set_mode`, `manual_rc`, `manual_release` on the server; Manual-tab visibility + pre-arm-bypass on the client.

## Telemetry dict (expanded)
Added to the broadcast: `SERVO1..4`, `THROTTLE_PCT`, `BAT_V/A/PCT`, `GPS_FIX/SATS/HDOP`, `EKF_COMPASS_VAR/POS_VAR/VEL_VAR`, `CURRENT_WP`, `WP_TOTAL`, `HOME_SET`, `HB_AGE_MS`, `GPS_AGE_MS`, `ESP32_AGE_MS`, `GCS_AGE_MS`, `WATCHDOG_*`, `FAILSAFE_TRIPPED`. Broadcast cadence raised from 3 s to 1 Hz. Legacy CSV log untouched; full dict also mirrored to `blackbox_<ts>.jsonl` for post-mortem.

## Mission planning additions
- Polygon fence upload via legacy FENCE_POINT protocol; sets `FENCE_ENABLE/ACTION/TYPE`.
- Lawnmower generator: axis-aligned horizontal sweeps with boustrophedon ordering; spacing in meters via UI input.
- Named mission templates save/load in `localStorage`.

## Map
Default base layer is now Esri World Imagery (satellite). Layer switcher offers Street (OSM), Topographic (OpenTopoMap), and OpenSeaMap as a transparent overlay for nautical features. Live mouse lat/lon/zoom in the map panel header.

## Files (all on `auto-nav-test`)
**New:** `jetson/static/js/telemetry_tab.js`, `safety.js`, `manual_tab.js`, `recording.js`, `mission_planning.js`; `jetson/tools/ws_peek.py`, `mock_server.py`.
**Modified:** `jetson/app.py`, `templates/index.html`, `static/css/style.css`, `static/js/webrtc.js`.

## Not yet verified
- Fence upload to a real Pixhawk.
- Gamepad flow (no controller available during dev).
- GCS MediaRecorder on a real WebRTC stream.
- Full battery threshold calibration (currently assumes 3S LiPo).

Full narrative in `Claude/session-logs/04-18-2026.md`.
