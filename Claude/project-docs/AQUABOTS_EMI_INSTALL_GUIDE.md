# AQUABOTS EMI Install Guide — Line-by-Line

**Team 26061 | Rev WG-3 / FAR-1 (04-12-2026)**
*Derived from EMI BOM Rev ISR-4b + WG-2 corrections (no I²C beads — pH is UART; new copper tape targets) + FAR-1 converter consolidation (ESP32 on 12V buck rail; 5V buck feeds Pixhawk POWER).*

Purpose: tells you exactly **which wire, which end, which component** for every EMI part in the system. Use this as your install checklist. Companion to `AQUABOTS_WIRING_GUIDE.md` — that doc governs routing, this one governs what to solder where.

---

## Universal Rules

1. **Parallel caps = same solder points.** Electrolytic + ceramic share the exact same (+)/(−) junction. Both must be present. Electrolytic catches low freq, ceramic catches high freq.
2. **Electrolytic polarity:** stripe / shorter lead = (−). Reversing = cap fails, sometimes violently. Check every one.
3. **Ceramics have no polarity.**
4. **Voltage rating is a ceiling, not a target.** 50V cap on a 5V rail is fine. Busbar-side (22–26V) needs 50V+ minimum to survive ESC spikes.
5. **Clip-on ferrites go on the (+) wire ONLY**, with one exception: F4 (12V buck output to ESP32) takes **both** wires together for common-mode filtering.
6. **Toroid (F1) = single pass.** One wire through the hole, no wrapping.
7. **Ferrite beads (F5) go in series.** Cut the signal wire, solder bead inline, shrink-tube.
8. **Lead length is everything.** Every mm of wire between a cap and the pin it protects is an inductor that kills HF filtering. Cut leads short.
9. **Copper tape shields grounded at ONE end only** (source end). Ungrounded = antenna. Both ends = ground loop.
10. **Install order:** busbar caps → input ferrites → wire the branches → output ferrites → output caps → sensor filtering → copper tape last → multimeter test → insert fuses.

---

## Step 1 — Busbar Bypass (highest priority, do first)

**Location:** across (+) and (−) busbar studs.

| Component | Value | Where exactly |
|---|---|---|
| **C1** | 1000uF / 35V+ electrolytic | Solder ring terminals to leads, mount on (+) and (−) busbar studs directly. Leads <1". Observe polarity. |
| **C2** | 100nF / 50V+ ceramic | **Parallel with C1** — same two studs, same solder joints. No polarity. Leads <0.5". |

Zip-tie to prevent vibration. Verify C2 is rated 50V+ (busbar sees 22–26V plus ESC transients).

---

## Step 2 — ESC / Motor Branch (P5) — 8 AWG

**This is the biggest noise source. Do not skip any of it.**

### 2a. Input ferrite — F1 (Hondark toroid)

- **Wire:** P5, the 8 AWG RED (+) lead from MIDI 60A fuse → ESC input.
- **End:** **ESC end.** Place within 2" of ESC input terminal.
- **How:** Pass the 8 AWG wire through the toroid center hole **once**. Single pass. Do NOT wrap multiple turns. Zip-tie to secure.

### 2b. Output caps at ESC input terminals

- **Location:** across ESC (+) and (−) power input terminals, <0.5" from ESC pads.

| Component | Value | Notes |
|---|---|---|
| **C3** | 470uF / 35V+ **LOW-ESR** electrolytic | Polarity matters. Low-ESR is critical **HERE ONLY** — handles high-current transients from ESC switching. |
| **C2** | 100nF / 50V+ ceramic | **Parallel with C3.** Same solder points. No polarity. |

---

## Step 3 — 12V Buck Branch (Jetson + Fan + ESP32 — most sensitive load set) — **UPDATED FAR-1**

The 12V buck now feeds three loads: the Jetson DC barrel, the cooling fan, and the ESP32-S3 VIN. Filtering is split: input ferrite at the buck, output caps at each load, plus a common-mode ferrite on the ESP32 run (the RF-sensitive branch).

### 3a. Input ferrite — F2 (Raogoodcx 13mm clip-on)

- **Wire:** P9, the 12 AWG RED (+) lead from ATO 3A fuse → 12V buck input.
- **End:** **buck end.** Within 2" of buck input terminal.
- **How:** Snap clip-on around the RED (+) wire **only** (not both wires). Close, tape/zip-tie shut.

### 3b. Output ferrite — F4 (Raogoodcx 6–13mm clip-on) on ESP32 run only

- **Wire:** P20, the 22 AWG pair from 12V buck output → ESP32-S3 VIN.
- **End:** **ESP32 end.** Within 2" of the ESP32 breakout board.
- **How:** Pass **BOTH** (+) and (−) wires through the ferrite **together**. Common-mode filtering. This is the one exception to the "+ only" rule. (Jetson barrel and fan runs do not need F4.)

### 3c. Output caps at Jetson DC barrel

- **Location:** across the (+) and (−) wires feeding the Jetson DC barrel plug, <1" from the plug.

| Component | Value | Notes |
|---|---|---|
| **C5** | 100uF / 25–50V electrolytic | Polarity matters. |
| **C2** | 100nF / 50V+ ceramic | **Parallel with C5.** |

### 3d. Output caps at ESP32 VIN

- **Location:** across ESP32 VIN and GND pins, <0.5" from the board.

| Component | Value | Notes |
|---|---|---|
| **C4** | 10uF / 25V+ electrolytic | VIN is 12V now — cap voltage rating must exceed 12V. Polarity matters. |
| **C2** | 100nF / 50V+ ceramic | **Parallel with C4.** Same solder points. |

> **ESP32 VIN range:** Most ESP32-S3 breakouts accept 5–12V on VIN via an onboard regulator. Confirm your board's VIN max before power-on; if it's <12V, add a dedicated 12V→5V regulator on P20 before the breakout. Fan runs off the same 12V output via its JST connector — no extra filtering.

---

## Step 4 — 5V Buck → Pixhawk POWER Branch — **NEW FAR-1**

The generic 5V buck now replaces the old dedicated 5V Power Module on the Pixhawk POWER port (DF13 6-pin). The Power Module had internal filtering; the generic buck does not — so this branch now needs its own output caps.

### 4a. Input ferrite — F2 (Raogoodcx 13mm clip-on)

- **Wire:** P11, the 12 AWG RED (+) lead from ATO 2A fuse → 5V buck input.
- **End:** **buck end.** Within 2" of buck input.
- **How:** Snap around RED (+) wire only.

### 4b. Output caps at Pixhawk POWER connector

- **Location:** across the +5V and GND pins of the DF13 6-pin Pixhawk POWER connector (or on the harness pair <1" from the connector).

| Component | Value | Notes |
|---|---|---|
| **C5b** | 47uF / 10V+ electrolytic | Polarity matters. Stabilises Pixhawk input through ESC calibration inrush. |
| **C2** | 100nF / 50V+ ceramic | **Parallel with C5b.** |

> **Brownout watch:** If the Pixhawk resets during ESC arm / calibration, the generic buck is sagging. Add a Schottky series diode + bulk cap at the POWER input, or revert this branch to a dedicated Pixhawk Power Module.

---

## Step 5 — Starlink Branch (P7, direct from busbar)

### 5a. Input ferrite — F3 (Raogoodcx 13mm clip-on)

- **Wire:** P7, the 12 AWG RED (+) lead from ATO 7.5A fuse → Starlink DC input.
- **End:** **fuse end.** Within 3" of the ATO fuse block (not the Starlink end — the run is long, so catch the noise near the source).
- **How:** Snap around RED (+) wire only.

### 5b. Output caps at Starlink DC plug

- **Location:** across the (+) and (−) wires at the Starlink power connector, <1" from the plug.

| Component | Value | Notes |
|---|---|---|
| **C7** | 100uF / 50V electrolytic (on hand) | Polarity matters. |
| **C2** | 100nF / 50V+ ceramic | **Parallel with C7.** |

---

## Step 6 — BEC → Servo Branch (output caps only, no ferrite)

- **Location:** across the (+) and (−) wires of the servo cable, <1" from the servo 3-pin connector.
- **Note:** caps go at the **servo end**, not the BEC end. The servo is an inductive noise source; the caps absorb noise at the servo.

| Component | Value | Notes |
|---|---|---|
| **C6** | 100uF / 50V electrolytic (on hand) | Polarity matters. |
| **C2** | 100nF / 50V+ ceramic | **Parallel with C6.** Shrink-tube the junction. |

---

## Step 7 — (Removed — Pixhawk filtering now covered by Step 4)

The old Step 7 skipped the Pixhawk branch because the dedicated 5V Power Module had internal filtering. Under FAR-1 the Pixhawk is fed from a generic 5V buck — that branch is now Step 4 and needs its own output caps.

---

## Step 8 — Sensor Signal Filtering

### 8a. S10 TDS Analog — **CRITICAL**

- **Component:** C2 (100nF / 50V+ ceramic)
- **Location:** between the ESP32 ADC pin (the one reading TDS) and ESP32 GND.
- **Distance:** **<0.25" from the ESP32 pin.** This one matters more than all the other sensor caps combined — ADC accuracy depends on it.
- **How:** Solder directly to the header pin on the ESP32 breakout. Shortest possible leads.

### 8b. S8 pH UART — **NO BEADS REQUIRED**

pH was originally specified as I²C (which required ferrite beads on SDA/SCL). The firmware (`firmware/main/sensor_bridge.c`) uses **UART at 9600 baud** instead, via the CAT6 bundle pair. UART at 9600 baud has no noise sensitivity that a bead would help with at this revision.

If the pool test shows UART framing errors with the motor running, add a single clip-on ferrite on the CAT6 at the ESP32 end — do not cut and splice beads.

### 8c. S9 1-Wire Temperature — OPTIONAL

- **Component:** C2 (100nF ceramic)
- **Location:** between the ESP32 1-Wire data pin and GND, <0.5" from the pin.
- **Priority:** low. Install if convenient. Not critical.

### 8d. S7 IMU / S11 GPS — **DO NOT INSTALL**

Both sensors are removed in WG-2 (replaced by Pixhawk built-in IMU and M8N GPS). Any ferrite beads or caps the old BOM specified for these lines are **not needed**. Skip entirely.

---

## Step 9 — Copper Tape Shielding

**Rules:** copper tape innermost → automotive self-adhesion tape (insulation) → split loom (mechanical). Ground drain wire at **ONE end only** (source). Leave 0.5" bare at connectors so the tape doesn't short to pins.

### Cables to wrap

| # | Target | Priority | Drain end (ground here, ONE end only) |
|---|---|---|---|
| 1 | **P20** — 12V buck → ESP32 (22 AWG pair) | HIGH | 12V buck GND terminal (source end) |
| 2 | **S1** — ESP32 → Pixhawk UART (22 AWG) | MEDIUM | ESP32 GND (source end) |

### Component bodies to wrap (NEW in WG-2)

Wrap the full body of each device in copper tape, then insulating tape. Solder a short drain pigtail (22–26 AWG, 1–2") from the copper tape surface to the specified ground point.

| # | Target | Priority | Drain ground |
|---|---|---|---|
| 3 | **ESC body** (replaces heat shrink) | HIGH | (−) busbar — single point |
| 4 | **BEC body** (Castle) | MEDIUM | (−) busbar — single point |
| 5 | **12V buck converter body** | MEDIUM | (−) busbar — single point |
| 6 | **5V buck converter body** | MEDIUM | (−) busbar — single point |

**Each component body gets its own drain wire to the (−) busbar. ONE drain per body, ONE end only. Never daisy-chain the drains together.**

### Do NOT wrap

- CAT6 bow sensor bundle (S8/S9/S10) — the CAT6 foil shield already handles it
- P5/P6 ESC-motor 3-phase wiring — noise source, not victim; ferrite + caps handle it
- P1–P4 4 AWG trunk — short, fat, low impedance; not worth shielding
- S7, S11 — sensors removed in WG-2
- S10 TDS individually — already inside the CAT6 foil

---

## Soldering Cheat Sheet (print this, tick as you go)

| ☐ | Step | Part(s) | Where exactly |
|---|---|---|---|
| ☐ | 1 | C1 + C2 parallel | Busbar (+)/(−) studs, leads <1" |
| ☐ | 2a | F1 toroid | ESC end of P5 (8 AWG +), <2" from ESC, single pass |
| ☐ | 2b | C3 + C2 parallel | ESC input terminals, <0.5" |
| ☐ | 3a | F2 clip-on | Buck end of P9 (12 AWG +), <2" from 12V buck |
| ☐ | 3b | F4 clip-on | ESP32 end of P20 (22 AWG pair, BOTH wires), <2" from ESP32 |
| ☐ | 3c | C5 + C2 parallel | Jetson DC barrel wires, <1" |
| ☐ | 3d | C4 + C2 parallel | ESP32 VIN / GND pins, <0.5" (C4 = 10uF/25V+) |
| ☐ | 4a | F2 clip-on | Buck end of P11 (12 AWG +), <2" from 5V buck |
| ☐ | 4b | C5b + C2 parallel | Pixhawk POWER DF13 connector, <1" |
| ☐ | 5a | F3 clip-on | Fuse end of P7 (12 AWG +), <3" from ATO block |
| ☐ | 5b | C7 + C2 parallel | Starlink DC plug wires, <1" |
| ☐ | 6 | C6 + C2 parallel | Servo connector wires, <1" from plug |
| ☐ | 8a | C2 ceramic | S10 TDS ADC pin → GND, <0.25" — **CRITICAL** |
| ☐ | 8b | — | S8 pH UART: no beads (UART, not I²C). Optional ferrite later if noisy. |
| ☐ | 8c | C2 ceramic | S9 1-Wire pin → GND (optional) |
| ☐ | 9-1 | Copper tape + drain | P20 cable, ground at 12V buck GND |
| ☐ | 9-2 | Copper tape + drain | S1 cable, ground at ESP32 GND |
| ☐ | 9-3 | Copper tape + drain | ESC body, ground to (−) busbar |
| ☐ | 9-4 | Copper tape + drain | BEC body, ground to (−) busbar |
| ☐ | 9-5 | Copper tape + drain | 12V buck body, ground to (−) busbar |
| ☐ | 9-6 | Copper tape + drain | 5V buck body, ground to (−) busbar |

---

## Total Part Count (sanity check before you start)

| Part | Qty needed |
|---|---|
| C1 (1000uF/35V+ electrolytic) | 1 |
| C2 (100nF/50V+ ceramic) | **~9** (1 busbar + 1 ESC + 1 ESP32 + 1 Jetson + 1 Pixhawk + 1 Starlink + 1 servo + 1 TDS + 1 optional 1-Wire) |
| C3 (470uF/35V+ LOW-ESR) | 1 |
| C4 (10uF/25V+ electrolytic) | 1 (ESP32 VIN at 12V) |
| C5 (100uF/25–50V electrolytic) | 1 (Jetson DC barrel) |
| C5b (47uF/10V+ electrolytic) | 1 (Pixhawk POWER input — NEW FAR-1) |
| C6 (100uF/16–50V electrolytic) | 1 (servo) |
| C7 (100uF/35–50V electrolytic) | 1 (Starlink DC) |
| F1 (Hondark MnZn toroid) | 1 |
| F2 (Raogoodcx 13mm clip-on) | 2 (12V buck input + 5V buck input) |
| F3 (Raogoodcx 13mm clip-on) | 1 (Starlink input) |
| F4 (Raogoodcx 6–13mm clip-on) | 1 (12V buck → ESP32 output pair) |
| F5 (BOJACK axial ferrite bead) | **0** (pH is UART — no beads) |
| Copper foil tape | 1 roll |
| Automotive self-adhesion tape | 1 roll |
| Split loom | as needed |

**⚠️ Do not energize the system until the ESC branch filter (F1 + C3 + C2 at Step 2) is fully installed.** Everything else can be phased in, but extended motor testing without the ESC toroid and low-ESR cap is the main thing to avoid per the changelog gating condition.
