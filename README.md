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
├── firmware/          ESP32-S3 swarm firmware (ESP-IDF v5.x, C)
│   ├── main/          All source files — see firmware/main/README.md
│   └── .devcontainer/ Docker dev environment for ESP-IDF
├── jetson/            Jetson Orin Nano onboard software (Python)
│   ├── app.py         Main integration server (Flask + MAVLink + sensors)
│   ├── webrtc_sender.py  Camera WebRTC pipeline
│   └── README.md      Setup and architecture docs
├── docs/              Project documents, power system changelog, wiring guides
├── reference/         Previous team's CAD files and reference code
└── README.md          This file
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
identity is stored in NVS flash. 9 modules covering the full swarm stack:

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

**Status:** Steps 1-6 hardware-verified. Steps 7-9 (obstacle sensing + avoidance)
coded, pending hardware test with ultrasonic sensor integration.

See `firmware/main/README.md` for build instructions, console commands, and
integration guide.

### `jetson/` — Jetson Orin Nano Onboard Software

Python code running on the Jetson. Handles:

- **Pixhawk MAVLink** — GPS, heading, speed, arm/disarm, throttle control
- **ESP32 sensor ingestion** — parses `TEMP:xx.x,SAL:xx.x,PH:xx.x` over serial
- **WebRTC camera streaming** — IMX219 via GStreamer/nvarguscamerasrc
- **Operator dashboard** — Flask web UI with Leaflet map, video, telemetry, motor controls
- **Telemetry logging** — CSV and WebSocket broadcast to ground station

See `jetson/README.md` for setup and architecture details.

---

## Communication Architecture

| Interface | Connection | Protocol | Status |
|---|---|---|---|
| IF-1 | ESP32 <-> Pixhawk | MAVLink / UART | Planned |
| IF-2 | Sensors -> ESP32 | I2C / ADC / 1-Wire | Active |
| IF-3 | ESP32 <-> Jetson | UART 115200 | Active |
| IF-4 | Drone <-> Cloud | Starlink / MQTT | Planned |
| IF-5 | Cloud <-> Ground Station | MQTT + WebSocket | Active |
| IF-6 | Drone <-> Drone | ESP-NOW | Complete |

**Swarm topology:** Hybrid star-mesh. Main drone = gateway (Starlink + ESP-NOW).
Followers = ESP-NOW only.

---

## Power System (Rev WG-2)

- **Demo battery:** 6S LiPo 22.2V / 6000mAh (~51 min endurance)
- **Production battery:** LiFePO4 24V / 100-200Ah (5+ hours)
- **Same wiring harness for both** — swap MRBF fuse element + adapter pigtail
- **Main fuse:** MRBF 100A (prod) / 40A (demo) -> Kill switch -> (+) Busbar
- **Motor branch:** 8 AWG, MIDI 60A fuse
- **EMI filtering** designed (Rev ISR-4b), all parts on hand, pending install

Full power system spec: `docs/AQUABOTS_POWER_SYSTEM_CHANGELOG.md`
Wiring guide: `docs/AQUABOTS_WIRING_GUIDE.md` (pending)

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

```bash
# SSH into the Jetson
ssh mayra@<jetson-ip>

# Activate the venv
source ~/AquaBotGUI_WebRTC/venv/bin/activate

# Start signaling server (terminal 1)
python3 signaling_server.py

# Start main server (terminal 2)
python3 app.py
```

Open `http://<jetson-ip>:5000` in a browser.

---

## Team

| Name | Role |
|---|---|
| John | ESP32-S3 swarm firmware, power system design, full hardware integration |
| Mayra | Ground station dashboard, Starlink comms, Jetson-side programming |
| Jamie | Water quality sensors (pH, salinity, temperature) |
| Robert | Propulsion / ESC hardware |
