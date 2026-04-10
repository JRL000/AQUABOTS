# AquaBot Jetson Orin Nano — Onboard Software

Code running on the **NVIDIA Jetson Orin Nano** aboard the main/gateway drone.
Handles the camera pipeline, Pixhawk MAVLink integration, ESP32 sensor ingestion,
WebRTC streaming, and the operator dashboard.

---

## Directory Layout

```
jetson/
├── app.py                 Main integration server (Flask + MAVLink + sensors + WebSocket)
├── webrtc_sender.py       Camera WebRTC pipeline (aiortc) + telemetry sender
├── signaling_server.py    WebRTC signaling relay (WebSocket, port 8765)
├── pixhawk_test.py        Standalone Pixhawk MAVLink diagnostic
├── telemetry_bridge.py    Simple serial-to-WebSocket bridge (utility)
├── templates/
│   └── index.html         Operator dashboard (Leaflet map, video, motor controls)
└── static/
    ├── css/style.css
    └── js/
        ├── webrtc.js      WebRTC client (video receive + zoom/record)
        └── bandwidth.js   iPerf3 network test trigger
```

---

## Key Components

### `app.py` — Main Integration Server

Monolithic server that runs on the Jetson and handles all subsystems:

- **ESP32 sensor ingestion** — reads `TEMP:xx.x,SAL:xx.x,PH:xx.x` from `/dev/ttyACM1` @ 115200 baud
- **Pixhawk MAVLink** — connects to `/dev/ttyACM0` @ 57600 baud, reads GPS, heading, speed, armed status
- **Motor control** — arm/disarm and throttle via MAVLink RC override (CH3, PWM 1100-1900)
- **WebSocket telemetry** — broadcasts JSON on port 8766 every 3 seconds
- **WebSocket control** — receives ARM/DISARM/throttle commands on port 8770
- **CSV logging** — writes telemetry to `/home/mayra/videos/telemetry_TIMESTAMP.csv`
- **Flask dashboard** — serves the operator UI on port 5000

### `webrtc_sender.py` — Camera + Telemetry WebRTC Sender

Runs the IMX219 camera pipeline via GStreamer/nvarguscamerasrc through aiortc WebRTC.
Also reads Pixhawk MAVLink and ESP32 sensor data, merging them into a single
telemetry stream. Supports digital zoom and on-demand video recording.

### `signaling_server.py` — WebRTC Signaling Relay

Simple WebSocket server (port 8765) that relays WebRTC offer/answer/ICE candidates
and forwards commands (zoom, record) between the browser and the Jetson sender.

### `pixhawk_test.py` — Pixhawk Diagnostic

Standalone script for testing the Pixhawk MAVLink connection. Prints GPS coordinates,
heading, speed, and GPS fix type. Useful for verifying the serial link independently.

---

## Ports

| Port | Protocol  | Service                        |
|------|-----------|--------------------------------|
| 5000 | HTTP      | Flask dashboard                |
| 8765 | WebSocket | WebRTC signaling               |
| 8766 | WebSocket | Telemetry broadcast            |
| 8770 | WebSocket | Motor control (ARM/throttle)   |

---

## Serial Devices

| Device        | Baud   | Connected To         |
|---------------|--------|----------------------|
| `/dev/ttyACM0` | 57600  | Pixhawk 4X (MAVLink) |
| `/dev/ttyACM1` | 115200 | ESP32 sensors        |

Note: device assignments may swap on reboot. Check `ls /dev/ttyACM*` if connections fail.

---

## Running

```bash
# Terminal 1 — signaling server
python3 signaling_server.py

# Terminal 2 — main server (starts Flask + sensor + Pixhawk threads)
python3 app.py

# Terminal 3 (optional) — WebRTC camera sender
python3 webrtc_sender.py
```

Open `http://<jetson-ip>:5000` in a browser for the dashboard.

---

## Dependencies

Installed in the venv on the Jetson (`/home/mayra/AquaBotGUI_WebRTC/venv/`):

- flask
- websockets
- pyserial
- pymavlink
- aiortc (for webrtc_sender.py)
- numpy, opencv (system-installed, NVIDIA build — **DO NOT pip install opencv-python**)

---

## Known Issues

- `controls.js` is empty — `sendArm()`, `sendDisarm()`, `setThrottle()` functions
  referenced in `index.html` are not yet implemented in JavaScript. Motor control
  currently works only via the WebSocket control server (port 8770).
- `app.py` has duplicate definitions of `Flask(__name__)` and `control_handler`
  (dead code at lines ~114 and ~243). Functional but should be cleaned up.
- Serial device paths (`ttyACM0`/`ttyACM1`) can swap between reboots.
