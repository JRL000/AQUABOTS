# Jetson Code Changes Log

This file tracks all modifications made to Mayra's Jetson code, with reasons.
Intended so John can accurately relay changes to Mayra.

---

## Status as of 2026-04-10

**No changes have been made to any of Mayra's existing files.**
All files in this directory were pulled directly from the Jetson
(`/home/mayra/AquaBotGUI_WebRTC/`) without modification.

The following new files were **added** (did not exist before):

---

## Additions

### `jetson/mavlink_router.py` — NEW FILE
**Date:** 2026-04-10
**Why:** Needed a way to bridge the Pixhawk serial port to QGroundControl on
the ground station PC over UDP/Tailscale. Mayra's `app.py` already has pymavlink
code for reading Pixhawk telemetry locally, but doesn't expose it as a MAVLink
endpoint that QGC can connect to directly.

This script runs alongside `app.py` as a separate process and forwards raw
MAVLink packets between `/dev/ttyACM0` (Pixhawk) and QGC over UDP port 14550.
It does not modify or interfere with `app.py`.

**Status:** Superseded by mavproxy on 2026-04-10 (see below).

---

## Tools Added to Venv

### `mavproxy` + `future` + `pynmeagps` — installed into `~/AquaBotGUI_WebRTC/venv/`
**Date:** 2026-04-10
**Why:** The custom Python router (`mavlink_router.py`) forwarded raw bytes but
QGC did not recognize the vehicle. mavproxy is the standard ArduPilot GCS proxy
tool — it correctly handles the MAVLink handshake and stream request protocol
that QGC requires to detect a vehicle.

**Install command:**
```bash
source ~/AquaBotGUI_WebRTC/venv/bin/activate
pip install mavproxy
```
(`future` and `pynmeagps` installed automatically as dependencies.)

**Does not affect:** camera pipeline, WebRTC.

---

## New Files Added to Jetson (not in AquaBotGUI_WebRTC/)

### `/home/mayra/mavproxy_launcher.py` — NEW FILE
**Date:** 2026-04-10
**Why:** mavproxy requires a pseudo-TTY to run reliably as a background process
(its readline console quits immediately without one). This launcher allocates a
fake PTY, starts mavproxy as a child process, strips terminal escape sequences,
and forwards clean output to stdout for logging.

**Does not affect:** any existing code.

### `/home/mayra/.config/systemd/user/mavproxy.service` — NEW FILE
**Date:** 2026-04-10
**Why:** Ensures mavproxy starts automatically when the Jetson boots (or after a
crash), without requiring manual SSH intervention. Replaces the manual screen
session used during development.

**To manage manually:**
```bash
systemctl --user status mavproxy
systemctl --user restart mavproxy
systemctl --user stop mavproxy
journalctl --user -u mavproxy -f   # live log
```

---

## Modifications to Mayra's Existing Files

### `app.py` — line 23: MAVLink source changed from serial to UDP
**Date:** 2026-04-10
**Original:**
```python
pixhawk = mavutil.mavlink_connection('/dev/ttyACM0', baud=57600)
```
**Changed to:**
```python
pixhawk = mavutil.mavlink_connection('udp:0.0.0.0:14552')
```
**Why:** Both `app.py` and `mavproxy` cannot hold `/dev/ttyACM0` simultaneously.
mavproxy now owns the serial port exclusively and forwards MAVLink to two UDP
endpoints: QGC at `100.78.157.73:14550` and app.py at `127.0.0.1:14552`.
app.py receives the same MAVLink data as before — just via UDP instead of serial.
All existing functionality (telemetry reading, RC override, arm/disarm, parameter
setting) works identically through this path.

**Backup saved at:** `~/AquaBotGUI_WebRTC/app.py.pre_udp_fix`

### `app.py` — line 20: ESP32 serial made fault-tolerant
**Date:** 2026-04-10
**Original:**
```python
ser = serial.Serial('/dev/ttyACM1', 115200, timeout=1)
```
**Changed to:**
```python
try:
    ser = serial.Serial('/dev/ttyACM1', 115200, timeout=1)
    print('[ESP32] Serial connected on /dev/ttyACM1')
except serial.SerialException:
    ser = None
    print('[ESP32] /dev/ttyACM1 not found — sensor data unavailable')
```
**Also added** a null-check guard at the top of `read_esp32()` so the thread
exits cleanly instead of crashing when `ser` is None.

**Why:** app.py crashed on startup whenever the ESP32 was not physically
connected. This prevented testing any other functionality (MAVLink, GUI,
camera) when the ESP32 is absent. With this fix, app.py starts and runs
fully — sensor values just stay at zero until the ESP32 is connected.

---

## Changes — 2026-04-10 (evening session)

### `app.py` — Pixhawk STATUSTEXT forwarding to browser
**Date:** 2026-04-10
**Added globals:**
```python
last_statustext = ""
last_statustext_sev = 6
current_wp = 0
```
**In `read_pixhawk()`:** STATUSTEXT handler now captures text + severity; MISSION_CURRENT handler
tracks current waypoint sequence number.
**In `telemetry_broadcast()`:** Broadcast now includes `STATUS`, `STATUS_SEV`, `CURRENT_WP` fields.
STATUS is cleared after each broadcast so only new messages appear.
**Why:** Browser had no way to see Pixhawk error messages. "EKF variance" and "Flight mode change
failed" were only in the server log, invisible to the operator.

### `app.py` — `resume` and `abort` control actions
**Date:** 2026-04-10
**Added to `control_handler`:**
- `resume`: calls `set_mode("AUTO")` — resumes mission from current waypoint (distinct from `go`
  which arms + starts fresh)
- `abort`: calls `disarm_vehicle()` — immediate disarm/stop
**Why:** Mission state machine in the GUI needs separate resume vs start, and an abort path.

### `static/js/controls.js` — full mission control state machine
**Date:** 2026-04-10
**Was:** Empty file (ARM/DISARM/throttle buttons didn't work, no mission control).
**Now:** Complete implementation with a 7-phase state machine:
`idle → uploaded → running ⇄ paused → returning ⇄ rth_paused → complete`

Key behaviours:
- Buttons shown/hidden per phase — only valid actions visible at each step
- START MISSION, RESUME, CONTINUE RETURN HOME, ABORT all require a confirm() dialog
- Telemetry drives phase transitions (MODE field from Pixhawk heartbeat)
- Suppress window (3–6 s) after button presses prevents telemetry flicker
- 8-second watchdog after GO: if Pixhawk doesn't confirm AUTO, reverts to `uploaded` with error
- HOLD from RTL → `rth_paused` state (separate from `paused`); RESUME sends RTL again
- Waypoint counter ("Waypoint X of Y") from `CURRENT_WP` telemetry field
- Pixhawk WARNING/ERROR messages shown in status box (severity ≤ 4; INFO filtered)
- Waypoints persist across page refresh via localStorage

### `templates/index.html` — mission control panel redesign
**Date:** 2026-04-10
**Replaced:** Old "Mission Planning" + "Auto Nav" sections (static GO/HOLD/RTH buttons always visible).
**New:** Phase badge (colored, shows exact state) + compact 3-button planning row + dynamic action
buttons (shown/hidden by state machine). Redundant "Mission Control" h3 removed.
missionStatus hidden via CSS `:empty` when no message.

### `static/css/style.css` — button spacing reduction
**Date:** 2026-04-10
Reduced global button `margin` from 6px → 4px and `padding` from 10px → 8px.
**Why:** Bottom row was too tall with 4 panels; tighter spacing fits everything cleanly.

---

## Pending Changes (deferred)

### `webrtc_jetson.py` — Pixhawk source needs to change from serial to UDP
**Status:** DONE (2026-04-10). Changed to `mavutil.mavlink_connection('udp:0.0.0.0:14553')`.
mavproxy_launcher.py updated to add `--out=udp:127.0.0.1:14553`.

### Startup process for full system
All four processes now run as systemd user services (auto-start on boot):
1. `mavproxy.service` — MAVProxy router
2. `aquabot-app.service` — Flask dashboard (port 5000)
3. `signaling.service` — WebRTC signaling server (ws:8765)
4. `webrtc.service` — camera stream

---

## Camera Issue — JetPack 6.2 Incompatibility (NEEDS FIX)

**Symptom:** `webrtc_jetson.py` starts and connects to the signaling server, but
`cv2.VideoCapture` always fails to return frames. The video panel in the browser
shows black. WebRTC negotiation itself is working (offer/answer/ICE succeed).

**Root cause:** JetPack R36.4.7 (JetPack 6.2) changed how Argus allocates NVMM
buffers. New Argus buffers no longer expose a DMA file descriptor (`dmabuf_fd = -1`).
OpenCV's GStreamer backend calls `NvBufSurfaceFromFd(fd)` on every captured frame to
map the buffer into CPU memory. With `fd = -1`, this call fails every time:
```
nvbuf_utils: dmabuf_fd -1 mapped entry NOT found
NvBufSurfaceFromFd Failed  (gstnvarguscamerasrc.cpp, threadExecute:734)
```
Every pipeline variant fails for the same reason — it is not a pipeline configuration
issue. `gst-launch-1.0` with `fakesink` works (fakesink never reads buffer data).
OpenCV's appsink fails because it tries to read the frame via `NvBufSurfaceFromFd`.

**Affected file:** `webrtc_jetson.py`, `CameraVideoTrack.__init__()` (lines ~77–86)

**Fix options (pick one):**
1. Replace `cv2.VideoCapture` with `jetson.utils.videoSource` — NVIDIA's JetPack
   6.x-native camera API. Requires `pip install jetson-utils` (or use the system
   install at `/usr/local/lib/python3.*/dist-packages/jetson/`).
   Example:
   ```python
   from jetson_utils import videoSource, cudaToNumpy, cudaDeviceSynchronize
   camera = videoSource("csi://0", argv=["--input-width=1280", "--input-height=720"])
   img = camera.Capture()
   frame = cudaToNumpy(img)
   ```
2. Use Python GStreamer bindings (`gi.repository.Gst`) with a custom appsink that
   accesses the buffer via the new `NvBufSurface` v2 API (not `NvBufSurfaceFromFd`).

**Current state in webrtc_jetson.py:** The `CameraVideoTrack` constructor adds a
v4l2 fallback and a real-frame test read so the process doesn't crash — it gracefully
sends black frames if the camera fails. The signaling/WebRTC pipeline is fully
functional; only the video content is black.

---

## Known Issues in Mayra's Existing Code (not changed, just documented)

These were observed during the code audit on 2026-04-10. Flagged for Mayra's
awareness — nothing was modified.

1. **`app.py` — duplicate `Flask(__name__)` definition** (lines ~114 and ~283).
   The second definition silently overwrites the first. No crash, but the
   `@app.route("/")` at line 117 is dead code.

2. **`app.py` — duplicate `control_handler` function** (lines ~243 and ~334).
   Same issue — second definition overwrites the first. The first version
   (which had slightly different logic) is silently discarded.

3. **`static/js/controls.js` — empty file.** The `index.html` dashboard
   references `sendArm()`, `sendDisarm()`, and `setThrottle()` functions
   that are supposed to be in `controls.js`, but the file is blank. The
   ARM/DISARM/Throttle buttons in the GUI will not work until this is filled in.

4. ~~**`static/js/webrtc.js` — signaling server IP hardcoded**~~ **ALREADY FIXED
   by Mayra.** webrtc.js now uses `window.location.hostname` dynamically.
