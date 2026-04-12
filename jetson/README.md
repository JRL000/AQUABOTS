# AquaBot Jetson Orin Nano — Onboard Software

Code running on the **NVIDIA Jetson Orin Nano** aboard the main/gateway drone.
Handles the camera pipeline, Pixhawk MAVLink integration, ESP32 sensor ingestion,
WebRTC streaming, mission planning, and the operator dashboard.

**Status:** deployed and operating. Four services run as systemd user units and
auto-start on boot. Live camera, telemetry, and mission control verified
04-11-2026.

---

## Directory Layout

```
jetson/
├── app.py                 Main integration server (Flask + MAVLink + sensors + WebSocket)
├── mavlink_router.py      Standalone Pixhawk serial <-> UDP bridge (superseded by mavproxy — kept for reference)
├── mavproxy_launcher.py   PTY-wrapped mavproxy launcher used by the systemd unit
├── webrtc_sender.py       Camera WebRTC pipeline (PyGObject GStreamer + aiortc)
├── signaling_server.py    WebRTC signaling relay (WebSocket, port 8765)
├── pixhawk_test.py        Standalone Pixhawk MAVLink diagnostic
├── telemetry_bridge.py    Simple serial-to-WebSocket bridge (utility)
├── CHANGES_FOR_MAYRA.md   Log of modifications made to the original GUI/Starlink code
├── systemd/               systemd user unit files for all 4 services
│   ├── mavproxy.service
│   ├── aquabot-app.service
│   ├── signaling.service
│   └── webrtc.service
├── templates/
│   └── index.html         Operator dashboard (Leaflet map, video, mission + motor controls)
└── static/
    ├── css/style.css
    └── js/
        ├── webrtc.js      WebRTC client (video receive + zoom/record)
        ├── controls.js    Mission state machine + ARM/DISARM/throttle
        └── bandwidth.js   iPerf3 network test trigger
```

---

## System Architecture

```
 Pixhawk 4X ──USB──> /dev/ttyACM0 ──owned by── mavproxy
                                                  │
                      ┌───────────────────────────┼─────────────────────────┐
                      │                           │                         │
                UDP 127.0.0.1:14552         UDP 127.0.0.1:14553       UDP <GCS>:14550
                      │                           │                         │
                      ▼                           ▼                         ▼
                  app.py                    webrtc_sender.py         QGroundControl
              (Flask + telemetry)          (telemetry overlay)        (over Tailscale)

 ESP32 ──USB──> /dev/ttyACM1 ──> app.py.read_esp32()  (TEMP:xx.x,SAL:xx.x,PH:xx.x @ 115200)

 IMX219 CSI ──> nvarguscamerasrc ──> nvvidconv ──> appsink ──> aiortc ──> browser
                (built directly in webrtc_sender.py using PyGObject — bypasses broken cv2.VideoCapture on JetPack 6.2)
```

`mavproxy` exclusively owns the Pixhawk serial port. Everything that consumes
MAVLink (app.py, webrtc_sender.py, QGroundControl) connects to a local or
remote UDP endpoint.

---

## Key Components

### `app.py` — Main Integration Server

Monolithic server that runs on the Jetson and handles all subsystems:

- **Pixhawk MAVLink (UDP)** — reads telemetry from `udp:0.0.0.0:14552` (fed by mavproxy). Parses GPS, heading, speed, armed status, flight mode, STATUSTEXT warnings/errors, and current mission waypoint (`MISSION_CURRENT`).
- **Mission upload** — full MAVLink mission protocol handshake (`MISSION_COUNT`, `MISSION_REQUEST_INT`, `MISSION_ITEM_INT`, `MISSION_ACK`). Applies `MOT_SLEWRATE` and `WP_SPEED` safety limits on upload.
- **Mission control actions** — `GO` (arm + AUTO), `HOLD` (LOITER), `RTH` (RTL), `RESUME` (re-enter AUTO from current WP), `ABORT` (immediate disarm).
- **Motor control** — ARM/DISARM and throttle via MAVLink RC override (CH3, PWM 1100-1900).
- **ESP32 sensor ingestion** — reads `TEMP:xx.x,SAL:xx.x,PH:xx.x` from `/dev/ttyACM1` @ 115200 baud. Fault-tolerant: if the ESP32 isn't connected, sensor values stay at 0 and the rest of the stack keeps running.
- **WebSocket telemetry** — broadcasts JSON on port 8766 every 3 seconds. Includes STATUS, STATUS_SEV, CURRENT_WP so the browser UI can surface Pixhawk warnings and track waypoint progress.
- **WebSocket control** — receives ARM/DISARM/throttle/mission commands on port 8770.
- **CSV logging** — writes telemetry to `/home/mayra/videos/telemetry_TIMESTAMP.csv`.
- **Flask dashboard** — serves the operator UI on port 5000.

### `webrtc_sender.py` — Camera + Telemetry WebRTC Sender

Runs the IMX219 camera pipeline and streams the video to the browser via aiortc.
Uses PyGObject GStreamer bindings (`gi.repository.Gst`) to build the
`nvarguscamerasrc → nvvidconv → appsink` pipeline directly and pull samples via
`sink.emit('pull-sample')`. This bypasses `cv2.VideoCapture`, which is broken on
JetPack 6.2 because Argus no longer exposes a DMA file descriptor and OpenCV's
GStreamer backend fails on `NvBufSurfaceFromFd(-1)`.

Also reads Pixhawk MAVLink (UDP 14553) and ESP32 sensor data and merges them
into the telemetry overlay. Supports digital zoom and on-demand video recording.

### `signaling_server.py` — WebRTC Signaling Relay

WebSocket server (port 8765) that relays WebRTC offer/answer/ICE candidates
and forwards commands (zoom, record) between the browser and the Jetson sender.

### `mavproxy_launcher.py` — Background mavproxy Runner

Allocates a pseudo-TTY, starts `mavproxy.py` as a child process, strips terminal
escape sequences, and forwards clean output to stdout. Required because
mavproxy's readline console exits immediately without a real TTY. Invoked by
`systemd/mavproxy.service`.

### `pixhawk_test.py` — Pixhawk Diagnostic

Standalone script for testing the Pixhawk MAVLink connection. Prints GPS,
heading, speed, and fix type. Useful for verifying the link independently of
the main stack.

### `static/js/controls.js` — Mission State Machine

7-phase state machine driving the operator UI:

```
idle → uploaded → running ⇄ paused → returning ⇄ rth_paused → complete
```

- Per-phase button visibility (only valid actions visible at each step)
- Confirmation dialog on START MISSION / RESUME / CONTINUE RETURN HOME / ABORT
- Telemetry drives phase transitions (MODE field from Pixhawk heartbeat)
- 8-second watchdog after GO — if Pixhawk does not confirm AUTO, reverts to `uploaded` with an error
- Suppress window (3–6 s) after button presses to prevent telemetry flicker
- Pixhawk WARNING/ERROR STATUSTEXT (severity ≤ 4) surfaced in the status box
- Waypoints persisted across page refresh via `localStorage`

---

## Running (systemd user services — preferred)

All four components run as systemd user units and auto-start on boot.

```bash
systemctl --user status mavproxy          # Pixhawk UDP router
systemctl --user status aquabot-app       # Flask + MAVLink + sensors (port 5000)
systemctl --user status signaling         # WebRTC signaling (port 8765)
systemctl --user status webrtc            # Camera stream

systemctl --user restart <unit>           # Restart a single service
journalctl --user -u <unit> -f            # Live log
```

Open `http://<jetson-ip>:5000` in a browser for the dashboard.

### Manual foreground run (for debugging only)

```bash
source ~/AquaBotGUI_WebRTC/venv/bin/activate

# stop the systemd unit first so only one instance holds the port
systemctl --user stop aquabot-app
python3 app.py
```

---

## Ports

| Port | Protocol  | Service                        |
|------|-----------|--------------------------------|
| 5000 | HTTP      | Flask dashboard                |
| 8765 | WebSocket | WebRTC signaling               |
| 8766 | WebSocket | Telemetry broadcast            |
| 8770 | WebSocket | Motor / mission control        |
| 14550| UDP       | mavproxy -> QGroundControl     |
| 14552| UDP       | mavproxy -> app.py             |
| 14553| UDP       | mavproxy -> webrtc_sender.py   |

---

## Serial Devices

| Device          | Baud   | Connected To                               |
|-----------------|--------|--------------------------------------------|
| `/dev/ttyACM0`  | 57600  | Pixhawk 4X — **owned exclusively by mavproxy** |
| `/dev/ttyACM1`  | 115200 | ESP32 sensors (`TEMP:xx.x,SAL:xx.x,PH:xx.x`) |

Note: device assignments may swap on reboot. Check `ls /dev/ttyACM*` if
connections fail and update the systemd units accordingly.

---

## Dependencies

Installed in the venv on the Jetson (`/home/mayra/AquaBotGUI_WebRTC/venv/`):

- flask
- websockets
- pyserial
- pymavlink
- mavproxy (+ future, pynmeagps auto-installed)
- aiortc (for webrtc_sender.py)
- PyGObject (system-installed — used by webrtc_sender.py for the GStreamer pipeline)
- numpy, opencv (system-installed NVIDIA build — **DO NOT `pip install opencv-python`**)

---

## Absolute Constraints — Camera Stack

The camera pipeline has hard constraints (documented on the Jetson at `~/DO_NOT_UPGRADE_CAMERA.md`):

- **NEVER** `apt upgrade nvidia-*` packages
- **NEVER** `pip install opencv-python`
- **NEVER** remove `nvidia-opencv`
- **NEVER** upgrade JetPack
- **NEVER** touch OpenCV, GStreamer, JetPack, or camera drivers
- **NEVER** run `sudo apt upgrade` (pulls nvidia-* updates)

If the camera pipeline breaks, the project is blocked.

### Camera recovery (if the stream goes black)

1. Check the CSI ribbon on both ends — contacts toward the board, latches closed.
2. Full power-cycle (not just reboot) so the kernel re-probes IMX219.
3. Verify: `sudo dmesg | grep imx219` — expect a `bound` line.
4. Check `systemctl --user status webrtc`.
5. Do **NOT** start `sudo systemctl start webrtc_jetson.service`. The correct
   service is the user-level `webrtc.service`; the system-level one conflicts
   and fails with `Failed to create CaptureSession`.

---

## Modifications Log

All modifications made to the original GUI / Starlink code are logged in
[`CHANGES_FOR_MAYRA.md`](CHANGES_FOR_MAYRA.md) with rationale and diffs.
Read that file before editing any of the files above.
