# AQUABOTS PROJECT — COMPREHENSIVE SUMMARY
## Communications & Power Systems (For Claude Code Context)

**Project:** AQUABOTS Aeropak — Autonomous Underwater/Surface Swarm Drones
**Course:** ENGR 498B Spring 2026, University of Arizona (Team 26061)
**Body last reviewed:** 02-25-2026
**Updated header:** 04-12-2026

---

## 0. UPDATES SINCE 02-25-2026

The body of this document is a snapshot from late February. This section captures what has landed since then so readers don't have to reconcile the two on their own. When the two conflict, this section governs.

### Swarm firmware (Section 1.2)

Steps 7, 8, and 9 are no longer "planned." All three are coded on the `auto-nav` branch:

- **Step 7 — Obstacle Sensor Scaffolding:** `firmware/main/obstacle_sense.c/h`. Sensor abstraction with pluggable driver, swarm-wide scan fusion, mock driver for bench testing.
- **Step 8 — Ultrasonic Distance Sensor Integration:** `firmware/main/a02yyuw.c/h`. Production driver for the DFRobot A02YYUW waterproof ultrasonic sensor (4-byte UART frame at 9600 baud). Supports up to four instances for 360° coverage; registers as an `obstacle_sense` driver.
- **Step 9 — Avoidance Policy:** `firmware/main/avoidance.c/h`. State machine with CLEAR / WARNING / DANGER states, suggested-alternate-bearing callback, configurable thresholds.

Swarm roadmap status is effectively 9/9 coded. Bench verification of the Step 1–6 behaviour still holds (RTT <5 ms, 0 % loss, leader election, TDMA slots, formation geometry). Step 7–9 modules are unit-tested with the mock driver; multi-node water verification with live ultrasonic sensors is the outstanding item.

### IF-3 (ESP32 ↔ Jetson) — ESP32 side now built

The interface table in Section 1.1 lists IF-3 as "Spec Week 8." The ESP32 side now has a real implementation: `firmware/main/sensor_bridge.c/h`.

- Reads DS18B20 temp (1-Wire GPIO 4), TDS/salinity (ADC1 CH0 / GPIO 1), Atlas EZO pH (UART1 GPIO 16/17).
- Streams `TEMP:%.2f,SAL:%.3f,PH:%.2f\n` at 115200 baud on UART2 (GPIO 47 TX / GPIO 48 RX) every 3 s.
- Salinity math uses a cubic EC polynomial with temperature compensation (ported verbatim from the team's prior Arduino prototype).
- All pins / baud / task timing are `#define`s at the top of the header for easy remapping.
- Managed components declared in `firmware/main/idf_component.yml` (`espressif/onewire_bus`, `espressif/ds18b20`).

Jetson side (`jetson/app.py:read_esp32`) already parses that exact CSV format and folds it into the telemetry JSON broadcast. IF-3 is code-complete both ends; hardware verification pending return of the board.

**Wiring note:** `AQUABOTS_WIRING_GUIDE.md` was patched 04-11-2026 to reflect UART on pH (S8 now a UART pair in the CAT6 bundle, not SDA/SCL). Atlas EZO pH supports both modes; confirm the EZO carrier is set to UART before first power-on.

### GUI / mission planning (net new since Feb 25)

Operator-facing browser GUI now owns the full mission lifecycle — no QGroundControl required at the pool.

- `jetson/app.py` — MAVLink mission upload protocol (`MISSION_COUNT` / `MISSION_REQUEST_INT` / `MISSION_ITEM_INT` / `MISSION_ACK`), GO / HOLD / RTH / RESUME / ABORT actions, STATUSTEXT forwarding, CURRENT_WP tracking, `MOT_SLEWRATE` and `WP_SPEED` safety limits.
- `jetson/controls.js` — 7-phase state machine (idle → uploaded → running ⇄ paused → returning ⇄ rth_paused → complete), per-phase button visibility, confirmation dialogs, 8-second heartbeat watchdog, waypoint persistence in `localStorage`.
- `jetson/mavlink_router.py` — Pixhawk serial → UDP bridge so `app.py`, QGC, and other MAVLink listeners can share the flight controller without fighting over `/dev/ttyACM0`.
- Four services auto-start on Jetson boot: `mavproxy`, `aquabot-app`, `signaling`, `webrtc`.

### Camera (Jetson)

JetPack 6.2 broke `cv2.VideoCapture` + `nvarguscamerasrc` — Argus stopped exposing a DMA fd so OpenCV's `NvBufSurfaceFromFd()` call silently fails. Fix: replaced OpenCV capture with PyGObject GStreamer (`gi.repository.Gst`, `sink.emit('pull-sample')`, `buf.map(Gst.MapFlags.READ)`) in `jetson/webrtc_sender.py`. Deployed 04-11-2026. If the camera goes black again, check the CSI ribbon cable first (full reseat both ends, contacts toward board), full power cycle, then verify `dmesg | grep imx219` shows `bound`.

### Off-water integration test (04-10-2026 / 04-11-2026)

With all electronics mounted inside the hull and Pixhawk bridged via MAVProxy over Tailscale: motor spins on GUI arm + throttle, rudder servo responds to GUI directional input, waypoints upload cleanly, mission state machine steps through its phases, GPS locks, telemetry displays live in the GUI, STATUSTEXT forwards in real time, full remote operation confirmed from an off-site network. In-water run did not happen — speed and maneuverability in water are the only outstanding verification items.

### Blockers before first AUTO-mode water run

- **Compass calibration.** Pixhawk EKF is flagging compass variance; AUTO mode won't engage until the cal spin is completed.
- **Multi-drone water verification** for the swarm stack.
- **Physical build-out** of the EMI filtering and the WG-2 plate ground / ESC under-plate mount (see `AQUABOTS_WIRING_GUIDE.md` — all parts on hand, none installed).

### Interface-table corrections to Section 1.1

- IF-3 status: "Spec Week 8" → **Both ends coded, HW verification pending.**
- IF-6 status: unchanged (✅ DONE), but Section 1.2 Steps 7–9 are now also complete.

### Telemetry-path clarification (Section 1.6)

Section 1.6 says telemetry is MQTT. That was the CDR plan. In practice the GUI-facing telemetry path is WebSocket + JSON from `jetson/app.py`, and the MAVLink side is UDP via MAVProxy. MQTT is still on the block diagram for the cloud uplink (IF-4 / IF-5) but is not in the current running stack. The swarm does **not** use MQTT — it is pure ESP-NOW between ESP32s.

---

## PROJECT OVERVIEW

AQUABOTS is a swarm of autonomous surface drones for environmental monitoring. Each drone carries sensors (pH, salinity, temperature), a camera, and communicates via ESP-NOW for local swarm coordination and Starlink for cloud/ground station uplink. The system uses a leader-follower architecture where the leader drone has a Starlink uplink and relays commands/data to follower drones via ESP-NOW mesh.

---

## 1. COMMUNICATIONS SYSTEM

### 1.1 Architecture

The communication system has **6 integration interfaces across 4 subsystems**:

| Interface | Connection | Protocol | Status |
|-----------|-----------|----------|--------|
| IF-1 | ESP32 ↔ Pixhawk | UART / MAVLink | Spec Week 8 |
| IF-2 | Sensors → ESP32 | I2C / ADC | Spec Week 8 |
| IF-3 | ESP32 ↔ Jetson | UART / Serial (115200) | Spec Week 8 |
| IF-4 | Drone ↔ Cloud | Starlink / MQTT | Spec Week 8 |
| IF-5 | Cloud ↔ Ground Station | MQTT + WebSocket | Spec Week 8 |
| IF-6 | Drone ↔ Drone | ESP-NOW | ✅ DONE |

### 1.2 Swarm Communication — ESP-NOW (IF-6)

**Platform:** ESP32-S3 (Xtensa dual-core @ 240 MHz)
**Framework:** ESP-IDF v5.5.x
**Protocol:** ESP-NOW (IEEE 802.11 Action Frames, Layer 2 MAC, connectionless)
**RTOS:** FreeRTOS
**Language:** C (embedded systems)

#### 9-Step Development Roadmap — Current Status: 6/9 Complete (67%)

**STEP 1: Modular Scaffolding ✅ COMPLETE**
- 9-module architecture, 20-file modular design
- ESP-NOW transport layer (2.4 GHz, 250 kbps)
- Packed binary struct packets (64 bytes) — 10x smaller than JSON
- Verified: RTT 4-5ms, RSSI -15 to -30 dBm, 0% packet loss
- Source files: `swarm_transport.c/h`

**STEP 2: NVS Node Provisioning ✅ COMPLETE**
- Persistent node identity in NVS flash (survives power cycles)
- Single firmware binary for all nodes, runtime node_id assignment (1-254)
- Console commands: `set_node_id`, `get_node_id`, `info`, `help`
- Source files: `node_config.c/h`

**STEP 3: Membership Discovery ✅ COMPLETE**
- HELLO broadcast protocol (2-second interval)
- Automatic peer discovery (no hardcoded MACs — zero-configuration)
- Dynamic member table (50 node capacity)
- Timeout detection (10 seconds), join/leave callbacks
- Verified: Discovery time 2-4 seconds, RSSI tracking -16 to -24 dBm
- Source files: `membership.c/h`

**STEP 4: Leader Election + TDMA ✅ COMPLETE**
- Distributed leader election (highest node_id wins)
- TDMA beacon broadcasts (1-second interval), 50ms time slots per node
- Automatic schedule generation, leader failover within 2-7 seconds
- Console commands: `leader`, `schedule`
- Source files: `leader_election.c/h`

**STEP 5: Command Engine ✅ COMPLETE**
- Command types: GOTO, HOLD, STOP, RESUME
- Thread-safe execution (mutex protection)
- Duplicate command detection, real-time status tracking
- Leader-only command sending enforced
- Verified: <50ms command latency, 100% success rate
- Console commands: `goto <x> <y> [heading]`, `hold`, `stop`, `resume`, `status`
- Source files: `command_engine.c/h`

**STEP 6: Formation Control ✅ COMPLETE (Verified Feb 09, 2026)**
- Four formation patterns: LINE, CHEVRON (wedge), CIRCLE, INDIVIDUAL
- Leader sets formation type + spacing, config broadcast via ESP-NOW
- Each node calculates own position from index (extensible function pointer pattern)
- Hardware verified test results:
  - LINE 2000mm: Leader (0,0), Follower (0,-2000) → PASS
  - WEDGE 2000mm: Leader (0,0), Follower (-1000,-2000) → PASS
  - WEDGE 500mm: Leader (0,0), Follower (-250,-500) → PASS
  - Spacing change: Scaled correctly → PASS
  - Non-leader command rejection: → PASS
- Console commands: `formation <type>`, `spacing <mm>`, `fmove <x> <y>`, `fstatus`

**STEP 7: Obstacle Sensor Scaffolding — PLANNED**
- Sensor interface abstraction layer
- Mock obstacle data API for testing
- Estimated ~300 lines code

**STEP 8: Ultrasonic Distance Sensor Integration — PLANNED**
- Real sensor driver, object detection
- Originally planned as mmWave radar, may use ultrasonic
- Estimated ~400 lines code

**STEP 9: Avoidance Policy — PLANNED**
- Collision avoidance algorithms, dynamic path planning
- Detection range target: 3m minimum, response time <500ms
- Estimated ~200 lines code

**FINAL STEP (after 9): Debugging and Stress Testing**

### 1.3 Swarm Architecture Details

**Topology:** Hybrid Star-Mesh ("Gateway & Swarm")
- Main Drone (Gateway): Starlink uplink + ESP-NOW Rx/Tx + Jetson Nano + ESP32
- Follower Drones (Swarm): ESP-NOW only (relays to main), sensors, Raspberry Pi + ESP32

**Routing:** Custom flooding algorithm with TTL=3 for multi-hop relay when direct LOS blocked

**Control Strategy:** "Virtual Rigid Body"
- Swarm treats leader as origin (0,0), moves as single fixed coordinate frame
- Follower derives target using leader's heading rotation matrix + offset vector
- PID controller drives motor thrust to zero distance error
- Failsafe: If data age > 3.0s → "Station Keep" (hold GPS position)

### 1.4 Performance Metrics (Verified)

| Metric | Spec | Achieved | Status |
|--------|------|----------|--------|
| Communication Range | 30m indoor | 30m+ (designed) | ✅ PASS |
| Discovery Time | <5 seconds | 2-4 seconds | ✅ PASS |
| Command Latency | <100ms | <50ms | ✅ PASS |
| RTT Latency | — | <5ms | ✅ PASS |
| RSSI | >-70 dBm | -16 to -24 dBm | ✅ PASS |
| Packet Loss | <5% | 0% | ✅ PASS |
| Max Swarm Size | 20-50 nodes | 50 (designed, tested 2) | ✅ PASS |
| Leader Election Time | <10 seconds | 5 seconds | ✅ PASS |
| TDMA Slot Duration | 50ms | 50ms | ✅ PASS |
| Throughput | — | 50 packets/sec | ✅ PASS |

### 1.5 Bandwidth Analysis

| Link | Available | Required | Margin |
|------|-----------|----------|--------|
| Swarm (ESP-NOW) | ~1,000 kbps | 10 kbps (2 drones) | 99% free |
| Satellite (Starlink) | ~5,000 kbps | 2,560 kbps (video+telemetry) | ~50% free |

### 1.6 Starlink Communication

- Starlink Mini unit (antenna + router in one)
- Direct power from 22.2V battery rail (Starlink Mini accepts 12-48V DC input)
- Ethernet connection to Jetson Orin Nano (100BASE-T, Cat5e, RJ-45)
- Worst-case tested speeds: Uplink 10 Mbps, Downlink 55 Mbps (tested in high Wi-Fi interference neighborhood)
- CDE-1 validated: Reliable two-way communication via Starlink uplink and GUI dashboard
- Video uplink: WebRTC
- Telemetry: MQTT

### 1.7 Code Quality

- Total production code: ~2,350 lines
- Modules complete: 6/9 (67%)
- Thread-safe: Yes (mutex protection throughout)
- Memory leaks: None detected
- Documentation: 767-line comprehensive README

---

## 2. POWER SYSTEM

### 2.1 Design Evolution (PDR → CDR → ISR)

**Original PDR Design (deprecated):**
- 24V LiFePO4 battery
- 48V boost converter + PoE injector to power Starlink
- 19V buck converter
- BMS (Battery Management System)
- Complex power chain

**CDR Design (major simplification):**
- Switched to 6S LiPo battery (22.2V, 6000mAh, 133.2 Wh)
- Eliminated 48V boost converter and PoE injector entirely
- Starlink Mini powered directly from 22.2V rail (accepts 12-48V)
- Eliminated BMS (LiPo doesn't need external BMS like LiFePO4)
- Simpler, lighter, more reliable

**ISR Design (current — fuse protection upgrades):**
- Core architecture unchanged from CDR
- Main fuse upgraded: 80A → 150A (MRBF fuse holder)
- Added dedicated 125A motor fuse (MIDI fuse block)
- Proper fuse blocks: MRBF + MIDI + ST Blade ATO
- Added thermal pads for heat management
- All parts ordered and awaiting delivery

**Post-ISR → FAR updates:**
- Wiring upgrades driven by ISR mentor feedback (fuse/wire coordination): main trunk 4 AWG, motor branch 8 AWG, all other busbar branches 12 AWG, signal/data 22 AWG. Data in §2.2 below is the FAR-1 rev.
- Converter consolidation (FAR-1): ESP32 moved onto the 12V buck rail (shared with Jetson + fan). The freed 5V buck now feeds the Pixhawk POWER port in place of a dedicated 5V Power Module. One fewer ATO branch, one fewer part.

### 2.2 Current Power Architecture (Rev FAR-1)

**Battery (production):** LiTime 24V LiFePO4 100–200Ah, 25.6V nominal (8S).
**Battery (demo):** Ovonic 6S LiPo, 22.2V nominal, 6000mAh, 133.2 Wh.
**Main Bus:** (+) Busbar → 22–26V Rail → (−) Busbar
**Safety:** MRBF 100A (prod) / 40A (demo) main fuse → Manual kill switch

**Power Distribution (single harness, swap MRBF element + pigtail between configs):**

| Load | Fuse | Wire Gauge | Voltage | Max Current | Cruise Power |
|------|------|-----------|---------|-------------|-------------|
| ESC → Motor (Apisqueen 5080) | MIDI 60A | 8 AWG (both +/−) | 22–26V direct | 54A | 60W |
| Starlink Mini (direct) | ATO 7.5A SB | 12 AWG | 22–26V direct | 4.7A | 70W |
| 12V Buck → Jetson + Fan + ESP32 VIN | ATO 3A SB | 12 AWG | 12V | 1.5A out / 0.9A in | 18W |
| 5V Buck → Pixhawk POWER (DF13) | ATO 2A SB | 12 AWG | 5V | 0.5A out / 0.15A in | 3W |
| BEC (Castle) → Rudder Servo | ATO 2A SB | 12 AWG | 7.4V | 1.0A | 5W |
| Sensors (pH / temp / TDS / ultrasonic) | via ESP32 3.3V reg | 26 AWG signal | 3.3V | 0.3A | 5W |

**Battery → MRBF → Kill Switch → Busbar trunk:** 4 AWG (Red+/Blk-). Demo uses a removable XT90 → 10–12 AWG pigtail on the MRBF input.

**Fuse coordination rule (every branch):** Max Load < Fuse Rating < Wire Ampacity. Full verification table and ampacity derivation in `AQUABOTS_POWER_SYSTEM_CHANGELOG.md` §1.5.

### 2.3 Power Budget Summary

| Subsystem | Max Power | Cruise Power | Max Current |
|-----------|-----------|-------------|-------------|
| Propulsion (motor) | 1200W | 60W | 54A |
| Comms (Starlink) | 105W | 70W | 4.7A |
| Compute (Jetson + Fan + ESP32) | 28W | 18W | 1.5A out |
| Flight Control (Pixhawk via 5V buck) | 5W | 3W | 1.0A out |
| Servo (BEC) | 8W | 5W | 1.0A |
| Payload (Sensors via ESP32 3.3V) | 6W | 5W | 0.3A |
| **TOTAL (battery-side)** | **~1361W** | **~155W** | **~61.3A** |

**Demo cruise endurance:** 133.2 Wh / 155W ≈ **51 minutes**
**Production endurance target:** 5+ hours (battery swaps)
**Safety margin:** 61.3A peak well within 100A prod / 40A demo main fuse and the LiFePO4 / LiPo discharge limits.

### 2.4 Signal & Data Interconnects

| Connection | Protocol | Signal | Cable | Connector |
|-----------|----------|--------|-------|-----------|
| ESP32 → Pixhawk (IF-1) | MAVLink / UART1 | TX/RX 3.3V | 22 AWG | JST-SH 4-pin |
| ESP32 → Jetson (IF-3) | UART2 115200 | TX/RX 3.3V | 22 AWG | JST-SH 4-pin |
| Pixhawk → ESC (S3) | PWM 50Hz | 3.3V logic | 22 AWG | Servo 3-pin |
| Jetson → Camera (CSI) | MIPI CSI-2 | LVDS diff | Ribbon | 15-pin FPC |
| Jetson → Starlink | Ethernet | 100BASE-T | Cat5e | RJ-45 |

> S3 is driven by the Pixhawk (ArduPilot Rover `MAIN OUT 3` throttle channel), not the ESP32. Earlier revisions of this document listed ESP32 → ESC PWM — that entry is superseded; the ESP32 is sensor + swarm comms only. Reference: `docs/PIXHAWK_ESC_MOTOR_WIRING.md`.

### 2.5 Parts Procurement (All Ordered as of ISR)

| Part | Qty | Price | Status |
|------|-----|-------|--------|
| 6S LiPo Battery | 1 | $66 | ORDERED |
| MRBF Fuse Holder | 1 | $25 | ORDERED |
| MIDI Fuse Block | 1 | $38 | ORDERED |
| ST Blade Fuse Block | 1 | $47 | ORDERED |
| 150A Fuse | 1 | $18 | ORDERED |
| 125A Fuse | 1 | $12 | ORDERED |
| Bus Bars (+/-) | 2 | $100 | ORDERED |
| Manual Kill Switch | 1 | $25 | ORDERED |
| Castle BEC (7.4V) | 1 | $47 | ORDERED |
| Thermal Pads + ATO Fuses + DC Pigtails | — | $39 | ORDERED |
| **Total** | | **$417** | |

---

## 3. SOFTWARE INTEGRATION FRAMEWORK

### 3.1 Overall Status: 5/14 major items complete (35%)

### 3.2 Five-Phase Integration Roadmap

**PHASE 1: Communications Layer ✅ COMPLETE**
- 1.1 ESP-NOW Transport Layer ✅
- 1.2 Node Identity Management ✅
- 1.3 Swarm Discovery Protocol ✅
- 1.4 Leader Election & TDMA ✅
- 1.5 Command Distribution ✅

**PHASE 2: Motion Control Integration 🟡 IN PROGRESS**
- 2.1 Propulsion Interface Layer 🔲 (motor control API, PWM, thruster mapping)
- 2.2 Navigation Controller 🔲 (waypoint nav, path planning, heading control)
- 2.3 HOLD Position Controller 🔲 (station-keeping, drift compensation)

**PHASE 3: Formation Control 🔲 PLANNED**
- 3.1 Formation Algorithm 🔲 (line, wedge, circle, column implementation)
- 3.2 Formation Maintenance 🔲 (error correction, stability, dropout handling)

**PHASE 4: Obstacle Avoidance 🔲 PLANNED**
- 4.1 Sensor Interface 🔲 (sensor driver, mock data)
- 4.2 Collision Avoidance 🔲 (detection, path replanning)

**PHASE 5: System Integration & Testing 🔲 PLANNED**
- 5.1 Hardware Integration Testing 🔲
- 5.2 Performance Validation 🔲

### 3.3 Integration Schedule

| Week | Task | Status |
|------|------|--------|
| 1-2 | ESP-NOW transport layer | ✅ Complete |
| 3 | Node provisioning | ✅ Complete |
| 4-5 | Membership discovery | ✅ Complete |
| 6-7 | Leader election + TDMA | ✅ Complete |
| 8 | Command engine | ✅ Complete |
| 9-10 | Propulsion interface layer | 🟡 Current |
| 11-12 | Navigation controller | 🔲 Upcoming |
| 13-14 | Formation algorithms | 🔲 Upcoming |
| 15-16 | Sensor integration | 🔲 Upcoming |
| 17-18 | Collision avoidance | 🔲 Upcoming |
| 19-20 | Full system integration testing | 🔲 Upcoming |

### 3.4 Critical Path

Communications ✅ → Propulsion 🔴 → Navigation → Formation → Avoidance → System Test

**Current Blocker:** Compass calibration (Pixhawk EKF variance) before AUTO mode will engage; in-water speed/maneuverability verification.
**Mitigation:** Swarm stack, mission planning GUI, and off-water propulsion chain are verified on the bench and ready for pool-side testing once compass is calibrated.

---

## 4. REQUIREMENTS VERIFICATION (SRVM)

### 4.1 Communications Requirements

| Requirement | Method | Status | Evidence |
|------------|--------|--------|----------|
| 4.4.2 Inter-Drone Comms | TEST | ✅ PASS | RTT <5ms, 0% packet loss |
| 4.4.2 Inter-Drone Comms | DEMONSTRATION | ✅ PASS | Auto-discovery, synchronized commands |
| 4.4.2 Inter-Drone Comms | ANALYSIS | 🟡 In Progress | Scalability modeling (Wk 9) |
| 4.4.2 Inter-Drone Comms | INSPECTION | 🔲 Planned | Hardware/antenna check (Wk 12) |
| 5.4.2 Inter-Drone Comms | — | ✅ ESP-NOW verified | Validate 100m range at pool test |
| 5.3.1 Survivability | TEST | 🟡 Partial | Comms pass (0% loss calm), stormy test Wk 9 |
| 5.4.3 Data Relay | DEMO | 🟡 Partial | Position data OK, sensor pipeline pending Wk 11 |
| 4.4.1 Autonomy & Control | DEMO | 🟡 Partial | Commands OK, formation control done (Step 6) |
| 5.4.6 Swarm Control | — | 🟡 Partial | ESP-NOW done, need ESP32→Jetson bridge + MQTT Wk 12 |
| 4.1.2 Swarm Control | DEMO | ✅ PASS | Leader election, coordinated execution |

---

## 5. KEY DESIGN DECISIONS & CHANGES THROUGHOUT PROJECT

1. **Power simplification (PDR→CDR):** Eliminated 48V boost converter and PoE injector for Starlink. Discovered Starlink Mini accepts 12-48V DC directly, so the 22.2V LiPo can power it without conversion. Major reduction in complexity, weight, cost, and failure points.

2. **Battery change (PDR→CDR):** Switched from 24V LiFePO4 with BMS to 6S LiPo (22.2V). LiPo offers better energy density for marine application.

3. **Camera change (PDR→CDR):** Replaced GoPro Hero 7 Black with IMX219 — lower power, lower latency, CSI interface to Jetson.

4. **Fuse upgrades (CDR→ISR):** Main fuse 80A→150A (MRBF), added dedicated 125A motor fuse (MIDI), proper fuse blocks, thermal management.

5. **Wiring upgrade (post-ISR):** Upgraded main power wiring from 14 AWG to 12 AWG per ISR judge recommendation.

6. **Follower drone simplification (CDR):** Follower drones use Raspberry Pi + ESP32 (no Starlink, no Jetson). Only the main/gateway drone has Starlink uplink.

7. **Obstacle sensor decision pending:** Originally planned mmWave radar (Step 8), may use ultrasonic distance sensor instead. Decision still open.

---

## 6. DELIVERABLES TIMELINE

| Deliverable | Date | Description |
|------------|------|-------------|
| Integrated Sensor Suite | 12/2/2025 | pH, temp, salinity sensors |
| Mounted Cameras | 12/2/2025 | IMX219 with storage/streaming |
| Communication Module | 1/22/2026 | Starlink integrated with all components & GS |
| Propulsion System | 2/19/2026 | Functional propulsion w/ motor control |
| Operational Ground Station | 3/3/2026 | GUI + backend for live data |
| Functional Hull Prototype | 3/5/2026 | Hull integrated with all components |
| Manual | 4/14/2026 | Documentation and user guides |
| Project Final Report | 5/5/2026 | Summary, system specs, results |

---

## 7. DOCUMENTS PRODUCED DURING DISCUSSIONS

The following documents were created through conversations in this project and are available in the project knowledge:

1. **ISR_SWARM_COMMUNICATIONS_SUMMARY.md** — Comprehensive summary of Steps 1-5 implementation, verification results, SRVM mapping, performance metrics, and technology stack details.

2. **SOFTWARE_INTEGRATION_ACTION_ITEM.md** — Full 5-phase integration roadmap with 14 items, dependencies, schedule, risk assessment, testing infrastructure, and success metrics.

3. **ISR_READINESS_CHECKLIST.md** — Pre-ISR preparation guide covering demo preparation, SRVM mapping clarity, range testing, propulsion integration planning, slide structure recommendations, and Q&A preparation.

4. **ISR Presentation Slides** — Power subsystem and communications subsystem slide decks were discussed and refined for the ISR presentation.

---

## 8. IMPORTANT NOTES FOR CLAUDE CODE

- Prefer **technical accuracy over promotional language**. Use verified test results and concrete metrics, not "braggy" stats like lines of code.
- The SRVM (System Requirements Verification Matrix) format is critical for formal engineering reviews.
- Generated documents should be **Markdown or Typst** (Typst for professional PDF compilation).
- The project uses **GitHub** for code management.
- ESP-IDF v5.5.x is the development framework — all swarm firmware is C for embedded systems.
- The ESP32-S3 firmware is a **single binary** that runs on all nodes; identity is provisioned at runtime via NVS.
- Formation control (Step 6) was completed and verified on hardware as of Feb 09, 2026, after the ISR_SWARM_COMMUNICATIONS_SUMMARY.md was written (which only covered Steps 1-5). The ISR slides reflect 6/9 steps complete.
- The next coding work is Steps 7-9 (obstacle sensing and avoidance) and the remaining integration phases (propulsion interface, navigation, etc.).
- Wiring was upgraded to 12 AWG post-ISR per judge recommendation — this is the most recent change.
