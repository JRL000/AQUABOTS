# AQUABOTS Hull Wiring Integration Guide

**Team 26061 — ENGR 498B Spring 2026**
**Rev WG-2 (corrected) | 2026-04-26**
*This document was previously labeled Rev WG-3 / FAR-1 (04-12-2026) with a converter-consolidation patch (ESP32 onto 12V buck rail; 5V buck replaces Pixhawk Power Module). That FAR-1 change was a paper architecture only and was never installed. This revision reverts the wire-ID swaps and converter consolidation back to the as-built WG-2 state: ESP32 on its own 5V buck (P13 input, P20 output); dedicated 5V Power Module on Pixhawk POWER (P9 input, P21 output); five ATO branches.*
*04-11-2026 patch (preserved): pH protocol corrected from I²C to UART to match `sensor_bridge.c`. Affects §3.2 (CAT6 pairs), §4.3 (sensor filtering), and §7 step 13.*

---

## ⚠️ Implementation Status (04-26-2026)

This guide is the **design spec**. Physical build is partial. Do not assume anything below is installed unless marked ✅.

| Subsystem | Status |
|---|---|
| Aluminum baseplate cut and fitted | ✅ DONE |
| Busbars (+/−) mounted on plate | ✅ DONE |
| Battery cutoff switch mounted | ✅ DONE |
| ATO fuse box mounted | ✅ DONE |
| 5V + 12V buck converters mounted | ✅ DONE |
| 5V Power Module (Pixhawk POWER) | ✅ DONE |
| Power trunk (batt → cutoff → fuses → busbars) | ✅ VERIFIED |
| ESC + Pixhawk powered (QGC calibrated, motor responds) | ✅ VERIFIED |
| Starlink / Jetson / Pixhawk / BEC mounting holes | 🔲 Plate not drilled |
| Servo mounting (on hull, not plate) | 🔲 Pending |
| Full system integration | 🔲 IN PROGRESS |
| **ESC under-plate mounting (WG-2)** | 🔲 DESIGN ONLY |
| **Plate grounded + Kapton top + thermal pads (WG-2)** | 🔲 DESIGN ONLY (parts on hand) |
| **Sensor consolidation: S7 + S11 removed (WG-2)** | ✅ FINALIZED (ESP32 firmware updated) |
| **EMI filtering (Rev ISR-4b caps/ferrites/copper tape)** | 🔲 ALL PARTS ON HAND, NONE INSTALLED |

**Gating condition:** No extended motor testing until F1 (Hondark ESC toroid) and C3 (470uF LOW-ESR) are physically installed. Short-duration auto-nav water test is OK.

> **Accuracy note:** The "FAR-1 converter consolidation" written into the prior WG-3 revision of this guide was a paper-only architecture change that was never installed. This revision reverts to the as-built WG-2 reality. If any other AQUABOTS doc still claims FAR-1 wire-ID swaps (ESP32 on 12V rail, P21 = generic 5V buck → Pixhawk, etc.), that doc is out of date — this guide governs.

---

## 1 — Hull Layout Reference

Hull: teardrop ~1m × 0.4m. Pointy end = bow, wide end = stern. 12×24" aluminum plate in forward-mid section (velcro mounted). ESP32-S3 on Meshnology breakout board on hull cap top plate (preserves IPEX antenna cable).

| Zone | Components | Position |
|---|---|---|
| Top Deck (bow-mid) | Starlink Mini, Camera | Above plate, sky-facing |
| Forward on Plate | (+) Busbar, (−) Busbar, MRBF, Kill SW, MIDI, ATO | First 6" of plate |
| Mid Plate (top) | 12V Buck, 5V Buck, 5V Power Module, BEC | Middle 8" of plate |
| Aft on Plate (top) | Jetson Orin Nano, Pixhawk 4X (built-in IMU + M8N GPS) | Last 6" of plate |
| **Mid/Aft Plate (UNDERSIDE)** | **ESC (WG-2)** | **Bottom surface above stern/motor area** |
| External Bow Mount | pH, Temp, TDS, Ultrasonic (submerged) | Below waterline, bow |
| Aft / Below Plate | Battery (demo or production) | Widest hull section |
| Stern | Motor (5080), Rudder Servo | Stern centerline |

**WG-2 changes:** GPS and IMU moved from external modules to Pixhawk built-ins (top deck Pixhawk position). ESC relocated from mid-plate topside to plate underside.

---

## 2 — Power Wiring

### 2.1 — Main Trunk (4 AWG)

| ID | From | To | Gauge | Length | Color | Fuse | Ring Terminal |
|---|---|---|---|---|---|---|---|
| P1 | Batt (+) | MRBF Holder In | 4 AWG | 6" | RED | MRBF 100A/40A | SC16-8 (M8) |
| P2 | MRBF Out | Kill Switch | 4 AWG | 6" | RED | — | SC16-6 (1/4") |
| P3 | Kill Switch | (+) Busbar | 4 AWG | 6" | RED | — | SC16-6 (1/4") |
| P4 | Batt (−) | (−) Busbar | 4 AWG | 12" | BLK | — | SC16-6 (1/4") |

*Ring terminal note:* 4 AWG wire is 19mm² welding cable (undersized vs 21.15mm²). Use SC16-8 for M8 battery studs, SC16-6 for 1/4" busbar studs. Do **not** use SC25.

**Demo adapter pigtail (removable):**

| ID | From | To | Gauge | Length | Color | Connector |
|---|---|---|---|---|---|---|
| D1 | XT90 (+) | MRBF input stud | 10–12 AWG | 6–8" | RED | XT90→ring |
| D2 | XT90 (−) | (−) Busbar | 10–12 AWG | 6–8" | BLK | XT90→ring |

### 2.2 — Motor Branch (8 AWG) — **WG-2**

| ID | From | To | Gauge | Length | Fuse | Notes |
|---|---|---|---|---|---|---|
| P5 | (+) Busbar | ESC Input (+) | 8 AWG | 10–12" | MIDI 60A | RED. Through MIDI block, **down through plate to underside ESC**. |
| P6 | (−) Busbar | ESC Input (−) | 8 AWG | 10–12" | — | BLK. Down through plate to underside ESC. |
| P17 | ESC (3φ) | Motor 5080 | 8 AWG | **4–8"** | — | 3 wires, 4mm bullets. **Shortened — ESC now directly above motor.** |

**Routing (WG-2):** ESC mounts on underside of aluminum plate at stern-ward end. 3-phase leads drop directly to motor in dedicated split loom. 8 AWG power feeds pass through a grommeted hole in the plate (insulated from now-grounded plate). This is still the primary EMI source, but the grounded plate now acts as a shield between ESC and topside electronics.

### 2.3 — Busbar Branch Circuits (ALL 12 AWG) — **WG-2 (five ATO branches)**

All non-motor busbar branches use 12 AWG for both (+) and (−). WG-2 carries five ATO branches: Starlink, 5V Power Module → Pixhawk, 12V buck → Jetson + fan, 5V buck → ESP32, BEC → servo.

| ID | Branch | To | Gauge | Length | Fuse | Notes |
|---|---|---|---|---|---|---|
| P7/P8 | Starlink (direct) | Starlink Mini DC | 12 AWG | 18–24" | ATO 7.5A SB | No converter. 12–48V. Plate→top deck. |
| P9/P10 | **5V Power Module** | Power Module input | 12 AWG | 4–6" | ATO 2A SB | Feeds Pixhawk POWER (DF13) via P21. Has internal filtering. |
| P11/P12 | 12V Buck | Buck input | 12 AWG | 4–6" | ATO 3A SB | Feeds Jetson + cooling fan. |
| P13/P14 | 5V Buck | Buck input | 12 AWG | 4–6" | ATO 1A SB | Feeds ESP32 VIN via P20. |
| P15/P16 | BEC (Castle) | BEC input | 12 AWG | 4–6" | ATO 2A SB | Feeds servo via P22. |

All (−) branches land on ATO block negative bus = electrically same node as (−) busbar. Single ground reference.

### 2.4 — Load-Side Connections — **WG-2**

| ID | From | To | Gauge | Length | Connector |
|---|---|---|---|---|---|
| P18 | 12V Buck | Jetson Orin Nano | 22 AWG | 6" | DC barrel |
| P19 | 12V Buck | Cooling Fan | 22 AWG | 4" | JST 2-pin |
| **P20** | **5V Buck** | **ESP32-S3 breakout VIN** | 22 AWG | 6" | Screw terminal |
| **P21** | **5V Power Module** | **Pixhawk 4X POWER port** | 22 AWG | 4" | DF13 6-pin |
| P22 | BEC (Castle) | Rudder Servo | 22 AWG | 18–24" | Servo 3-pin |
| P23 | ESP32 3.3V | Sensors (all) | 26 AWG | varies | DuPont/JST |
| P24 | Jetson 3.3V | Camera IMX219 | Ribbon | 3" | 15-pin FPC |

> **P20 vs P21 — separate branches with the same 22 AWG gauge.** P20 = 5V buck → ESP32 (with F4 common-mode ferrite per §4.2). P21 = 5V Power Module → Pixhawk POWER (no added EMI components; Power Module has internal filtering).
> **Pixhawk telemetry note:** the Power Module provides analog V/I telemetry on the POWER port ADC pins (V_BAT pin 3, I_BAT pin 4) — Pixhawk gets MAVLink `BATTERY_STATUS` automatically.

### 2.5 — Fuse Coordination — **WG-2**

| Branch | Max Load | Fuse | Wire Ampacity | Status |
|---|---|---|---|---|
| Trunk (prod) | 61.3A | 100A | 4 AWG 135A | PASS |
| Trunk (demo) | 40A gov | 40A | 10–12 AWG 41–55A | PASS |
| ESC/Motor | 54A | 60A | 8 AWG 73A | PASS |
| Starlink | 4.7A | 7.5A | 12 AWG 41A | PASS |
| 5V Power Module → Pixhawk | 0.15A | 2A | 12 AWG 41A | PASS |
| 12V Buck → Jetson + Fan | 0.85A | 3A | 12 AWG 41A | PASS |
| 5V Buck → ESP32 | 0.10A | 1A | 12 AWG 41A | PASS |
| BEC/Servo | 1.0A | 2A | 12 AWG 41A | PASS |

Derivation: 12V buck output = Jetson + fan ~15.6W; at 90% efficiency → ~17.3W input → 0.78A at 22.2V demo / 0.68A at 25.6V prod. 5V buck output = ESP32 breakout ~1W (3.3V regulator from 5V VIN, sensors and radio); at 90% efficiency → ~1.1W input → 0.05A at 22.2V demo / 0.04A at 25.6V prod. 5V Power Module to Pixhawk → ~2.5W output → ~2.8W input → 0.13A. All comfortably within their ATO fuses with room for startup inrush.

---

## 3 — Signal & Data Wiring

### 3.1 — Compute-Zone Interconnects — **WG-2**

| ID | From | To | Gauge | Protocol | Length | Connector |
|---|---|---|---|---|---|---|
| S1 | ESP32 UART1 | Pixhawk (IF-1) | 22 AWG | MAVLink UART 3.3V | 4–6" | JST-SH 4-pin |
| S2 | Pixhawk TELEM2 | Jetson (IF-3) | 22 AWG | UART 115200 3.3V | 4–6" | JST-SH 4-pin |
| S3 | Pixhawk PWM | ESC Signal | 22 AWG | PWM 50Hz | **8–12"** | Servo 3-pin |
| S4 | Jetson CSI | Camera IMX219 | Ribbon | MIPI CSI-2 LVDS | 3" | 15-pin FPC |
| S5 | Jetson Eth | Starlink Mini | Cat5e/6 | 100BASE-T | 12–18" | RJ-45 |
| ~~S7~~ | ~~ESP32 I2C~~ | ~~MPU6050 IMU~~ | — | — | — | **REMOVED — Pixhawk built-in IMU** |

**S3 routing (WG-2):** PWM now has to travel from Pixhawk (top of plate, aft) around the plate edge to ESC on the underside. Route through a dedicated small grommet, not the same hole as the 8 AWG power. Keep physically separated from motor power to the extent possible.

**S3 source:** Confirmed Pixhawk (ArduPilot Rover mode), not ESP32 direct GPIO. ✅ Verified with QGC calibration.

### 3.2 — Bow Sensor Bundle via Shielded CAT6

Shielded CAT6 patch cable runs from ESP32 area through hull to external bow sensor mount. Carries 3 signal lines (S7 removed in WG-2, so 1 pair now spare).

| Pair | Signal Line (ID) | Wire A | Wire B | Destination |
|---|---|---|---|---|
| 1 | S8 — pH UART RX | UART RX (module TX → ESP32) | GND | Atlas EZO-pH + isolation board |
| 2 | S8 — pH UART TX | UART TX (ESP32 → module RX) | 3.3V VCC | Atlas EZO-pH + isolation board |
| 3 | S9 — Temperature | 1-Wire DATA | GND | DS18B20 (waterproof) |
| 4 | S10 — TDS Conductivity | Analog signal | GND | TDS module (0–3.3V) |

**Protocol note (WG-2 patched 04-11-2026):** pH uses **UART at 9600 baud**, not I²C. Atlas EZO-pH supports both modes — the firmware (`firmware/main/sensor_bridge.c`) uses UART on ESP32 GPIO 16 (RX) and GPIO 17 (TX). Configure the EZO carrier for UART mode before first power-on.

**CAT6 shield grounding:** Ground foil shield at ESP32 end only (source). Leave bow end floating. Drain wire to ESP32 GND at breakout.

### 3.3 — Remaining Sensor Lines — **WG-2**

| ID | From | To | Gauge | Protocol | Length | Connector |
|---|---|---|---|---|---|---|
| ~~S11~~ | ~~ESP32 UART~~ | ~~NEO6MV2 GPS~~ | — | — | — | **REMOVED — Pixhawk M8N GPS** |
| S12 | ESP32 GPIO | DFRobot Ultrasonic | 26 AWG | Digital I/O | 18–24" | DuPont 4-pin |

S12 routes along hull wall to bow, separated from motor power lines. No dedicated top-deck GPS run needed anymore.

---

## 4 — EMI Filtering Placement

**Status:** All parts on hand (~$50 order complete). None physically installed. Install before extended motor testing.

> **Authoritative install procedure:** `AQUABOTS_EMI_INSTALL_PROCEDURE.md` (Rev WG-2). This section is the design summary; the procedure has the step-by-step.

### 4.1 — Busbar Bypass Caps

| Part | Value | Placement | Status |
|---|---|---|---|
| C1 | 1000uF / 35V+ electrolytic | Across (+)/(−) busbar studs, leads <1" | ON HAND |
| C2 | 100nF / 50V+ ceramic | Parallel with C1, same studs | ON HAND |

### 4.2 — Per-Branch Ferrites & Caps — **WG-2**

| Branch | Input Ferrite | Output Caps |
|---|---|---|
| ESC/Motor (P5) | F1: Hondark toroid (38×19×13mm) on 8 AWG (+), <2" from ESC, single pass | C3: 470uF LOW-ESR + C2 at ESC input |
| 5V Power Module → Pixhawk (P9 → P21) | None — Power Module has internal filtering | None — do **not** add caps at the DF13 connector. |
| 12V Buck → Jetson + Fan (P11 → P18 / P19) | F2: 13mm clip-on on 12 AWG (+), input | C5: 100uF/35V + C2 at Jetson barrel. Fan no extra filter. |
| 5V Buck → ESP32 (P13 → P20) | F2: 13mm clip-on on 12 AWG (+), input | F4: 6–13mm clip-on on 22 AWG ESP32 output pair (common-mode); C4: 100uF/16V + C2 at ESP32 VIN |
| Starlink (P7) | F3: 13mm clip-on on 12 AWG (+) | C7: 100uF/50V + C2 at DC plug |
| BEC→Servo (P15→P22) | — | C6: 100uF/50V + C2 at servo |

*Rules:* Clip-ons on (+) wire only, except F4 (both wires, common-mode). F1 toroid single pass only. Low-ESR critical at ESC position only. **The Pixhawk POWER branch (P9/P21) carries no added caps because the dedicated 5V Power Module has internal filtering — adding bulk at the DF13 risks oscillation against the Module's regulation loop.**

### 4.3 — Sensor Signal Filtering — **WG-2**

| Signal | Filter | Placement | Priority |
|---|---|---|---|
| S10 (TDS) | 100nF ceramic pin-to-GND | <0.25" from ESP32 ADC pin | **CRITICAL** |
| S8 (pH UART) | None required at 9600 baud. If noise observed in pool test, add a clip-on ferrite on the CAT6 at the ESP32 end. | ESP32 end of CAT6 breakout | LOW (defer) |
| S9 (1-Wire) | 100nF ceramic pin-to-GND | <0.5" from ESP32 pin | Optional |
| ~~S7 (IMU I2C)~~ | ~~BOJACK beads~~ | — | **REMOVED (S7 deleted)** |
| ~~S11 (GPS)~~ | ~~100nF cap~~ | — | **REMOVED (S11 deleted)** |

**Total BOJACK ferrite beads required: 0** (pH moved from I²C to UART — WG-2 originally called for 2 beads on SDA/SCL, no longer needed).

### 4.4 — Copper Tape Shielding — **WG-2**

| Cable / Component | Priority | Drain Ground | Notes |
|---|---|---|---|
| **P20**: 5V Buck → ESP32 | HIGH | 5V buck GND (source) | Wrap before loom |
| S1: ESP32 → Pixhawk UART | MEDIUM | ESP32 GND | Short, but near ESC path |
| **ESC body** | **HIGH (WG-2)** | **(−) busbar** | **Replaces heat shrink. Wrap ESC body, drain to (−) busbar, ONE end only.** |
| **BEC body** | **MEDIUM (WG-2)** | **(−) busbar** | **Wrap, drain to (−) busbar, ONE end only.** |
| **12V buck body** | **MEDIUM (WG-2)** | **(−) busbar** | **Wrap, drain to (−) busbar, ONE end only.** |
| **5V buck body** | **MEDIUM (WG-2)** | **(−) busbar** | **Wrap, drain to (−) busbar, ONE end only.** |
| **5V Power Module body** | **MEDIUM (WG-2)** | **(−) busbar** | **Wrap, drain to (−) busbar, ONE end only.** Even though the Module has internal filtering, the switching converter still radiates. |
| CAT6 bundle (S8/S9/S10) | — | Foil shield handles it | No extra tape |
| ~~S7 / S11 UART~~ | — | — | **REMOVED (sensors deleted)** |
| ~~S10 individual wrap~~ | — | — | **REMOVED (CAT6 foil now covers)** |
| P5/P6 motor 3φ | SKIP | — | Noise source; split loom only |
| P1–P4 trunk | SKIP | — | Short, low-Z |

**Ground rule:** Drain wire grounded at **ONE end only** (source end). Ungrounded = antenna. Both ends = ground loop.

---

## 5 — Plate as EMI Shield (NEW in WG-2)

The 12×24" aluminum mounting plate is grounded and used as a conductive shield between the ESC (mounted underneath) and the topside electronics (Jetson, Pixhawk, ESP32, converters, Power Module).

**Status: DESIGN ONLY. Parts on hand. Not yet implemented.**

| Element | Spec | Status |
|---|---|---|
| Plate ground jumper | 12 AWG, plate → (−) busbar, single point only | ON HAND |
| Kapton tape top surface | 2" wide, full coverage; double layer under ring terminals / bolt heads | ON HAND |
| Thermal pads (converter footprints) | Dielectric silicone, under 12V buck, 5V buck, BEC, 5V Power Module | ON HAND (confirmed insulating) |
| ESC underside thermal pad | Between ESC case and plate bottom | ON HAND |
| ESC splash guard | Conformal coat OR closed-cell foam wrap | ON HAND |

**Critical rules:**
- **Single ground point only** — no second plate-to-ground connection anywhere. Ground loops will wreck the whole filtering scheme.
- Kapton goes **under** every component that sits on the topside. The plate is now live ground; a scraped trace or a bare ring terminal edge = dead short.
- ESC is now the lowest component in the hull. It **will** see splash. Waterproofing is mandatory, not optional.

---

## 6 — Wire Routing Channels

| Channel | Wires | Path |
|---|---|---|
| Centerline (hull floor) | 4 AWG trunk, 8 AWG motor feed | Battery → busbars; busbars → through plate → ESC (underside). Dedicated loom. |
| **Plate underside** | **ESC 3-phase leads, ESC power feed** | **ESC → motor, short run in split loom** |
| Port hull wall | 12 AWG branches (P7–P16) | Busbars → converters. Short runs. |
| Starboard hull wall | 22–26 AWG signals, CAT6 | ESP32 → bow. Opposite wall from power. |
| Vertical / top deck | P7/P8 Starlink, S5 Ethernet | Plate → top deck pass-throughs |

**Critical separation:** Signal wires (22–26 AWG, CAT6) must stay ≥12" from 8 AWG motor power. The grounded plate helps but does not replace physical separation.

---

## 7 — Assembly Sequence (WG-2)

**Plate preparation (before any components mounted):**

- **A1.** Apply Kapton tape to entire top surface of aluminum plate. Double-layer under locations where ring terminals or bolt heads will contact.
- **A2.** Install thermal pads at converter footprints (12V buck, 5V buck, BEC, 5V Power Module).
- **A3.** Attach 12 AWG plate ground jumper (ring terminal end to plate bolt, other end prepped for (−) busbar — land in step 4).

**Main assembly:**

1. Verify all connections de-energized.
2. Build trunk: P1–P3 (MRBF → kill switch → (+) busbar), then P4 ((−) busbar).
3. Land plate ground jumper from A3 on (−) busbar.
4. Busbar bypass caps: C1+C2 in parallel on studs. Leads <1". Zip-tie.
5. Install ATO fuses (leave MRBF and MIDI empty).
6. Wire all 12 AWG branches P7–P16 from busbars to converters (five ATO branches per §2.3).

**ESC under-plate mounting (NEW in WG-2):**

- **6a.** Apply thermal pad to ESC underside, mount ESC to bottom surface of plate at stern-ward end.
- **6b.** Drill/grommet hole through plate for 8 AWG power feed. Route P5 (+) and P6 (−) through grommet to ESC.
- **6c.** Drill separate small grommet hole for S3 PWM signal. Route from Pixhawk around plate edge or through dedicated hole to ESC.
- **6d.** Apply conformal coat to ESC PCB OR wrap ESC body in closed-cell foam splash guard.

**Continuing:**

7. Input ferrites: F1 toroid on P5 (ESC), F2 clip-ons on P11 (12V buck in) and P13 (5V buck in), F3 clip-on on P7 (Starlink). **No clip-on on P9** — Power Module has internal filtering.
8. Wire motor branch P5/P6 through MIDI block to ESC.
9. Wire load-side P17–P24 (converters → devices). 12V buck fans out two ways (Jetson barrel, fan JST); 5V buck goes to ESP32 VIN; 5V Power Module goes to Pixhawk POWER (DF13 6-pin).
10. Output ferrite F4 on P20 (5V buck → ESP32 22 AWG pair, common-mode).
11. Output caps: C3+C2 at ESC, C4+C2 at ESP32 VIN, C5+C2 at Jetson, C6+C2 at servo, C7+C2 at Starlink. **No caps at the Pixhawk POWER connector.**
12. CAT6 bow sensor bundle: route ESP32 → bow. Break out pairs. Ground shield at ESP32 GND only.
13. Sensor filtering: C2 on TDS ADC pin (S10). No ferrite beads on pH UART at this revision — if pool-test noise warrants it, add a clip-on ferrite on the CAT6 at the ESP32 end later.
14. Remaining signals: S1, S2, S3, S12.
15. Copper tape wrapping: P20, S1, **ESC body, BEC body, 12V buck body, 5V buck body, 5V Power Module body** (WG-2). All grounded at ONE end only (source or (−) busbar).
16. Final inspection: all terminals tight, polarity correct, no stray strands, no cap shorts, **no topside ring terminal contacting bare plate**.
17. Insert MIDI 60A fuse element.
18. Insert MRBF fuse element **LAST** (this energizes the system).
19. Multimeter test at each load point before powering devices.

---

## 8 — Wire Cut List — **WG-2**

| Gauge | Color | Cut Length | Qty | Labels / Purpose |
|---|---|---|---|---|
| 4 AWG | RED | 8" | 3 | P1, P2, P3 (trim to 6" after crimp) |
| 4 AWG | BLK | 14" | 1 | P4 (trim to 12") |
| 8 AWG | RED | 14" | 1 | P5 (busbar → through plate → underside ESC +) |
| 8 AWG | BLK | 14" | 1 | P6 (busbar → through plate → underside ESC −) |
| 8 AWG | any ×3 | 10" | 3 | P17 three-phase ESC → motor |
| 12 AWG | RED | 8" | 5 | P7, P9, P11, P13, P15 short branch + (Starlink, Power Module, 12V buck, 5V buck, BEC) |
| 12 AWG | BLK | 8" | 5 | P8, P10, P12, P14, P16 short branch − |
| 12 AWG | BLK | 6" | 1 | Plate ground jumper → (−) busbar (WG-2) |
| 12 AWG | RED | 26" | 1 | P7 Starlink + (trim to 18–24") |
| 12 AWG | BLK | 26" | 1 | P8 Starlink − |
| 22 AWG pair | — | 6" | 5 | P18, P19, P20, P21 (load-side power: Jetson, fan, ESP32 VIN, Pixhawk POWER) plus one spare |
| 22 AWG pair | — | 24" | 1 | P22 BEC → servo |
| 22 AWG pair | — | 6" | 2 | S1, S2 (compute-zone signals) |
| 22 AWG pair | — | 12" | 1 | S3 PWM (Pixhawk → underside ESC) |
| ~~26 AWG 4-wire 5"~~ | — | — | — | **REMOVED — S7 IMU deleted** |
| ~~26 AWG 2-wire 20"~~ | — | — | — | **REMOVED — S11 GPS deleted** |
| 26 AWG 4-wire | — | 24" | 1 | S12 Ultrasonic (bow run) |
| CAT6 shielded | — | 30" | 1 | Bow sensor bundle (S8/S9/S10) |
| 10–12 AWG | RED+BLK | 8" ea | 1 ea | D1/D2 demo adapter pigtail |

*WG-2 note:* Five ATO branches (P7, P9, P11, P13, P15). Wire cut quantities reflect that.

---

## 9 — Pending Items

**Carryover from WG-1:**
- [ ] Verify Starlink Mini DC connector type — may need custom pigtail
- [ ] Confirm pH isolation board (Atlas EZO-pH galvanic protection)
- [ ] Install EMI parts; no extended motor testing until F1 + C3 in place
- [ ] Motor inrush test — confirm MIDI 60A holds during pool startup
- [ ] Jetson boot inrush test — confirm ATO 3A holds on the 12V rail
- [ ] Waterproofing / conformal coating plan

**Carryover from WG-2:**
- [ ] Drill baseplate for Starlink, Jetson, Pixhawk, BEC, Power Module mounting
- [ ] Apply Kapton to plate top surface
- [ ] Install thermal pads at converter footprints (12V buck, 5V buck, BEC, Power Module)
- [ ] Land 12 AWG plate ground jumper on (−) busbar
- [ ] Mount ESC on plate underside with thermal pad + splash guard
- [ ] Drill grommet holes for 8 AWG ESC power feed and S3 PWM
- [ ] Verify servo operation with Pixhawk before mounting to hull
- [ ] Full integration test: Jetson + Pixhawk + ESP32 + BEC + servo + Power Module
- [ ] **First auto-nav water test** (ArduPilot Rover + Starlink telemetry, no sensors)
- [ ] Physically install all EMI filtering before extended motor testing
- [ ] Confirm S3 PWM pin assignment on Pixhawk MAIN OUT (ArduPilot Rover default)

**FAR-1 reverted (2026-04-26):** the FAR-1 converter consolidation (ESP32 onto 12V buck rail; 5V buck → Pixhawk POWER replacing the Power Module) was a paper-only design that was never installed. Revisited and rejected — the Pixhawk telemetry V/I loss and the Power Module's internal filtering both made the FAR-1 trade-off unattractive once the parts count constraint relaxed. WG-2 stays.

---

*Companion documents:*
- *`AQUABOTS_POWER_SYSTEM_CHANGELOG.md` — full revision history (FAR-1 walked back; current state is WG-2)*
- *`AQUABOTS_EMI_FILTERING_BOM.pdf` (Rev ISR-4b) — BOM, placement, soldering instructions*
- *`AQUABOTS_EMI_INSTALL_PROCEDURE.md` (Rev WG-2) — single-doc install procedure for the EMI work*
- *`AQUABOTS_JETSON_CHANGELOG.md` (Rev JS-1) — Jetson software audit*
