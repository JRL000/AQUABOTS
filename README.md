# AQUABOTS — Team 26061

**University of Arizona ENGR 498B — Spring 2026**

Autonomous surface vehicle (ASV) swarm platform for environmental monitoring.
Three drones operate as a coordinated swarm using ESP-NOW for inter-node
communication. The main/gateway drone carries a Jetson Orin Nano, Starlink Mini,
IMX219 camera, and Pixhawk 4X flight controller; follower drones run a
Raspberry Pi + ESP32-S3.

---

## Repository Layout

```
AQUABOTS/
├── firmware/               ESP32-S3 swarm firmware (ESP-IDF v5.x, C)
│   ├── main/               All source files — see firmware/main/README.md
│   └── .devcontainer/      Docker dev environment for ESP-IDF
├── jetson/                 Jetson Orin Nano onboard software (Python)
│   ├── app.py              Main integration server (Flask + MAVLink + sensors)
│   ├── webrtc_sender.py    Camera WebRTC pipeline (PyGObject GStreamer)
│   ├── mavproxy_launcher.py  PTY-wrapped mavproxy for the systemd unit
│   ├── mavlink_router.py   Standalone serial<->UDP bridge (kept for reference)
│   ├── signaling_server.py WebRTC signaling relay
│   ├── systemd/            User unit files for all four services
│   ├── templates/, static/ Operator dashboard (Flask + Leaflet)
│   └── README.md           Setup and architecture docs
├── docs/                   Power system changelog, Pixhawk ESC wiring, misc
├── Claude/
│   ├── project-docs/       Project-level specs (power system, wiring guide, summaries, handoff)
│   └── session-logs/       Dated work logs
├── reference/              Previous team's CAD files and reference code
└── README.md               This file
```

---

## Hardware Overview

| Component | Main/Gateway Drone | Follower Drones |
|---|---|---|
| Compute | NVIDIA Jetson Orin Nano | Raspberry Pi |
| Flight Controller | Pixhawk 4X (ArduPilot Rover) | — |
| Comms MCU | ESP32-S3 | ESP32-S3 |
| Connectivity | Starlink Mini | — |
| Camera | IMX219 (CSI) | — |
| ESC / Motor | 80A ESC / Apisqueen 5080 | TBD |
| Sensors | pH (Atlas EZO), TDS, DS18B20 temp, ultrasonic | Same |
| Battery (demo) | Ovonic 6S LiPo 22.2V / 6Ah | — |
| Battery (production) | LiTime 24V LiFePO4 100-200Ah | — |

---

## Subsystems

### `firmware/` — ESP32-S3 Swarm Firmware

Written in C with ESP-IDF v5.5.x and FreeRTOS. All boats run the same binary;
identity is stored in NVS flash. 10 modules covering the full swarm stack:

| Module | Description |
|---|---|
| `node_config` | NVS-backed node identity (node_id 1-254) |
| `swarm_transport` | ESP-NOW send/receive, ping/ack diagnostics |
| `membership` | Peer discovery, heartbeat, active member table |
| `leader_election` | Highest-node-id election with TDMA scheduling |
| `scheduler` | TDMA slot coordination (50 ms slots) |
| `command_engine` | Command parsing, routing, execution (GOTO/HOLD/STOP/RESUME) |
| `formation` | Line, wedge, circle, column patterns with configurable spacing |
| `obstacle_sense` | Pluggable sensor abstraction with swarm-wide scan fusion |
| `a02yyuw` | DFRobot A02YYUW ultrasonic sensor UART driver |
| `avoidance` | State-machine collision avoidance (CLEAR/WARNING/DANGER) |

Plus one peripheral I/O module:

| Module | Description |
|---|---|
| `sensor_bridge` | DS18B20 + TDS + Atlas EZO pH reader; streams `TEMP/SAL/PH` CSV to Jetson over UART2 @ 115200 |

**Status:** Steps 1-6 hardware-verified on two-node bench (sub-5 ms RTT, 0 % packet loss,
deterministic leader election, formation geometry unit-tested). Steps 7-9
(obstacle sensing + avoidance) coded and unit-tested with the mock driver —
multi-node water verification with live ultrasonic sensors is the outstanding
item. `sensor_bridge` built 04-11-2026, hardware verification pending.

See `firmware/main/README.md` for build instructions, console commands, and
integration guide.

### `jetson/` — Jetson Orin Nano Onboard Software

Python code running on the Jetson. Handles:

- **Pixhawk MAVLink** — GPS, heading, speed, arm/disarm, throttle, STATUSTEXT + current-waypoint forwarding. Full mission protocol (upload + GO/HOLD/RTH/RESUME/ABORT). Serial port owned by `mavproxy`; all consumers read UDP endpoints.
- **ESP32 sensor ingestion** — parses `TEMP:xx.x,SAL:xx.x,PH:xx.x` over serial, fault-tolerant if ESP32 absent
- **WebRTC camera streaming** — IMX219 via PyGObject GStreamer (bypasses broken `cv2.VideoCapture` on JetPack 6.2)
- **Operator dashboard** — Flask + Leaflet UI with 7-phase mission state machine, video, telemetry, motor + mission controls
- **Telemetry logging** — CSV and WebSocket broadcast to ground station
- **Deployment** — four systemd user services auto-start on boot (`mavproxy`, `aquabot-app`, `signaling`, `webrtc`)

**Status:** deployed and operating on the Jetson; camera + mission + telemetry
verified 04-11-2026. AUTO-mode entry + mission start fixed 04-12-2026 (see
`jetson/CHANGES_FOR_MAYRA.md`). Outstanding: motor does not spin despite
Pixhawk commanding full throttle PWM — hardware/ESC investigation open.

See `jetson/README.md` for setup and architecture details.

---

## Communication Architecture

| Interface | Connection | Protocol | Status |
|---|---|---|---|
| IF-1 | ESP32 <-> Pixhawk | MAVLink / UART | Planned |
| IF-2 | Sensors -> ESP32 | 1-Wire / ADC / UART | Active (pH is UART, not I²C) |
| IF-3 | ESP32 <-> Jetson | UART 115200 | Code complete, hardware-verification pending |
| IF-4 | Drone <-> Cloud | Starlink + Tailscale | Active (Tailscale mesh over Starlink; no MQTT broker in this path) |
| IF-5 | Cloud <-> Ground Station | HTTP/WebSocket over Tailscale | Active |
| IF-6 | Drone <-> Drone | ESP-NOW | Complete |

**Swarm topology:** Hybrid star-mesh. Main drone = gateway (Starlink + ESP-NOW).
Followers = ESP-NOW only.

---

## Power System (Rev FAR-1 / WG-3)

- **Demo battery:** 6S LiPo 22.2V / 6000mAh (~51 min endurance)
- **Production battery:** LiFePO4 24V / 100-200Ah (5+ hours)
- **Same wiring harness for both** — swap MRBF fuse element + adapter pigtail
- **Main fuse:** MRBF 100A (prod) / 40A (demo) -> Kill switch -> (+) Busbar
- **Motor branch:** 8 AWG, MIDI 60A fuse
- **Converter consolidation (FAR-1):** ESP32 now runs off the 12V buck rail alongside the Jetson + fan. The freed 5V buck feeds the Pixhawk POWER port (replaces the dedicated 5V Power Module). Four ATO branches total: 7.5A Starlink, 3A 12V buck, 2A 5V buck (Pixhawk), 2A BEC/servo.
- **EMI filtering** designed (Rev ISR-4b + FAR-1 updates), all parts on hand, pending install.

Full power system spec: `docs/AQUABOTS_POWER_SYSTEM_CHANGELOG.md` (Rev FAR-1)
Wiring guide: `Claude/project-docs/AQUABOTS_WIRING_GUIDE.md` (Rev WG-3)

---

## Quick Start

### Firmware (ESP32-S3)

```bash
cd firmware
idf.py set-target esp32s3
idf.py build
idf.py -p <PORT> flash monitor
```

Provision node identity at the serial console:
```
swarm> set_node_id <1-254>
```

### Jetson

All four services auto-start on boot as systemd user units. Normal use
requires nothing more than powering the Jetson up.

```bash
# SSH into the Jetson (Tailscale IP)
ssh mayra@100.76.1.26

# Check status of the four services
systemctl --user status mavproxy aquabot-app signaling webrtc

# Live log
journalctl --user -u <unit> -f
```

Open `http://<jetson-ip>:5000` in a browser for the operator dashboard.

For manual debug runs, stop the corresponding systemd unit first so it
doesn't fight over ports / serial devices. See `jetson/README.md` for the
full architecture.


## Authorship

All software in this repository was written by John Lopez (JRL0101), unless noted below. That includes:

- **Jetson ground station**: `jetson/app.py`, the web GUI, mission authoring (fences, survey generator, templates), safety/E-Stop/admin flow, MAVLink/mavproxy integration, WebRTC video, systemd services, and deployment scripts
- **ESP32 firmware**: swarm membership, leader election, formation control, `sensor_bridge`, and `pixhawk_link`
- **Hardware documentation**: power system, wiring guide, and EMI install procedure

**Prior team work this builds on:**
- Sensor calibration and salinity math in `firmware/main/sensor_bridge.c` are ported from Jamie Ledbetter's Arduino/MicroPython sensor prototype (`Jamie/`, `Sensor_DataLog.py`).
- The Jetson GUI began as a modification of Mayra's original GUI/Starlink code (see `jetson/CHANGES_FOR_MAYRA.md`).
