# AQUABOTS Power System — Master Reference & Changelog

**Team 26061 | ENGR 498B Spring 2026**
**Last Updated:** 04-12-2026 (Rev FAR-1)

---

## 1. CURRENT CONFIGURATION (Rev FAR-1)

### 1.1 Dual-Config Concept

The wiring harness is designed ONCE for full production specs. Two battery configurations share the same harness:

| Parameter | Production | Demo |
|-----------|-----------|------|
| **Battery** | LiTime 24V 100–200Ah LiFePO4 | Ovonic 6S LiPo 22.2V / 6Ah |
| **Voltage** | 25.6V nominal (8S LiFePO4) | 22.2V nominal (6S LiPo) |
| **Connection** | M8 bolt posts → 4 AWG ring terminals | XT90 → adapter pigtail → harness |
| **Main Fuse** | MRBF **100A** | MRBF **40A** (swap element only) |
| **Motor Fuse** | MIDI **60A** | MIDI **60A** (same) |
| **Trunk Wire** | 4 AWG Red/Blk (permanent harness) | 10–12 AWG pigtail (adapter only) |
| **Endurance** | 5+ hours (battery swaps) | ~51 min (133.2 Wh / 155W) |
| **Adapter Pigtail** | Not needed | XT90♀ → 10–12 AWG → ring terminal (6–8") |

**To switch configs:** Swap MRBF fuse element + connect/disconnect adapter pigtail. No rewiring.

**Demo constraint:** MRBF 40A limits max system draw — motor cannot sustain 54A full throttle. This is correct/safe behavior for a 6Ah LiPo through 12 AWG leads.

### 1.2 Main Trunk

```
Battery → MRBF Fuse (100A prod / 40A demo) → Kill Switch (Manual) → (+) Busbar
Battery (−) → (−) Busbar
```

| # | From | To | Gauge | ~Length | Color | Fuse | Connector | Ring |
|---|------|-----|-------|--------|-------|------|-----------|------|
| P1 | Batt (+) | MRBF Holder | 4 AWG | 6" | RED | MRBF 100A | Ring→M8 | 3/8" |
| P2 | MRBF Out | Kill Switch | 4 AWG | 6" | RED | — | Ring→lug | 3/8" |
| P3 | Kill Switch | (+) Busbar | 4 AWG | 6" | RED | — | Ring→stud | 1/4" |
| P4 | Batt (−) | (−) Busbar | 4 AWG | 12" | BLK | — | Ring→M8 | 1/4" |

**Demo adapter pigtail (removable):**

| # | From | To | Gauge | ~Length | Color | Fuse | Connector | Ring |
|---|------|-----|-------|--------|-------|------|-----------|------|
| D1 | XT90♀ (+) | MRBF input stud | 10–12 AWG | 6–8" | RED | MRBF 40A* | XT90♀→ring | 3/8" |
| D2 | XT90♀ (−) | (−) Busbar | 10–12 AWG | 6–8" | BLK | — | XT90♀→ring | 1/4" |

*Swap MRBF element only.

### 1.3 Branch Circuits (All Branches — Same for Both Configs)

| # | Branch | From | To | Gauge (+) | Gauge (−) | Fuse | Max Load | Cruise |
|---|--------|------|-----|-----------|-----------|------|----------|--------|
| P5/P6 | ESC→Motor | Busbar | ESC | **8 AWG** | **8 AWG** | **MIDI 60A** | 54A | 60W |
| P7/P8 | Starlink (direct) | Busbar | Starlink Mini | **12 AWG** | **12 AWG** | ATO 7.5A SB | 4.7A | 70W |
| P9/P10 | 12V Buck→Jetson+Fan+ESP32 | Busbar | 12V Buck | **12 AWG** | **12 AWG** | ATO 3A SB | 0.9A in | ~18W |
| P11/P12 | 5V Buck→Pixhawk | Busbar | 5V Buck | **12 AWG** | **12 AWG** | ATO 2A SB | 0.15A in | ~3W |
| P13/P14 | BEC→Servo | Busbar | BEC (Castle) | **12 AWG** | **12 AWG** | ATO 2A SB | 1.0A | 5W |

**Consolidation note (FAR-1):** ESP32 is now powered off the 12V buck rail alongside the Jetson + fan (previously had its own 5V buck branch from the busbar). The 5V buck previously feeding the ESP32 now feeds the Pixhawk directly, replacing the dedicated 5V Power Module on the Pixhawk POWER port. One fewer ATO branch.

**Starlink note:** NO converter in path. Starlink Mini accepts 12–48V DC directly. Both 22.2V (demo) and 25.6V (prod) are in range.

### 1.4 Load-Side Connections (Converter → Device)

| # | From | To | Gauge | ~Length | Connector |
|---|------|-----|-------|--------|-----------|
| P17 | ESC (3-phase) | Motor (Apisqueen 5080) | 8 AWG | 10" | Bullet 4mm |
| P18 | 12V Buck | Jetson Orin Nano | 22 AWG | 6" | DC barrel |
| P19 | 12V Buck | Cooling Fan | 22 AWG | 4" | JST 2-pin |
| P20 | 12V Buck | ESP32-S3 breakout VIN | 22 AWG | 6" | Screw terminal |
| P21 | 5V Buck | Pixhawk 4X FC (POWER port) | 22 AWG | 4" | DF13 6-pin |
| P22 | BEC (Castle) | Rudder Servo | 22 AWG | 8" | Servo 3-pin |
| P23 | ESP32 3.3V reg | Sensors (all) | 26 AWG | varies | DuPont / JST |
| P24 | Jetson 3.3V reg | Camera (IMX219) | Ribbon | 3" | 15-pin FPC |

> **Pixhawk telemetry note:** Using a generic 5V buck instead of a dedicated Pixhawk Power Module means the flight controller no longer receives analog battery voltage / current telemetry on the POWER port. If battery monitoring via MAVLink `BATTERY_STATUS` is required, either (a) route a voltage / current sense line into a spare Pixhawk ADC channel, or (b) swap back to a Power Module on this branch. Not required for the current mission profile.

### 1.5 Fuse Coordination Verification

Every branch passes: **Max Load < Fuse Rating < Wire Ampacity**

| Branch | Max Load | Fuse | Wire | Wire Ampacity | ✅ |
|--------|----------|------|------|---------------|---|
| Trunk (prod) | 61.3A | 100A | 4 AWG | 135A | PASS |
| Trunk (demo) | 40A (governed) | 40A | 10–12 AWG | 41–55A | PASS |
| ESC/Motor | 54A | 60A | 8 AWG | 73A | PASS |
| Starlink | 4.7A | 7.5A | 12 AWG | 41A | PASS |
| 12V Buck in (Jetson+Fan+ESP32) | 0.9A | 3A | 12 AWG | 41A | PASS |
| 5V Buck in (Pixhawk) | 0.15A | 2A | 12 AWG | 41A | PASS |
| BEC/Servo | 1.0A | 2A | 12 AWG | 41A | PASS |

**Buck input-current derivation (12V Buck branch):**

Output side: Jetson + fan 1.3A @ 12V = 15.6W; ESP32 breakout (onboard regulation from 12V VIN) ~0.15A @ 12V ≈ 1.8W. Total output ≈ 17.4W.
Input side at 90% buck efficiency: 19.3W. At 22.2V demo → 0.87A. At 25.6V prod → 0.76A.
ATO 3A slow-blow gives ~3.4× steady-state margin and absorbs Jetson boot + buck input-cap inrush.

**Buck input-current derivation (5V Buck branch):**

Output side: Pixhawk 4X ~0.5A @ 5V = 2.5W.
Input side at 90% buck efficiency: 2.8W. At 22.2V → 0.13A. At 25.6V → 0.11A.
ATO 2A slow-blow leaves wide headroom for Pixhawk + peripheral bus startup.

### 1.6 Power Budget

| Subsystem | Voltage | Max Power | Cruise Power | Max Current |
|-----------|---------|-----------|-------------|-------------|
| Propulsion (Motor) | 22–26V | 1200W | 60W | 54.0A |
| Comms (Starlink) | 22–26V direct | 105W | 70W | 4.7A |
| Compute (Jetson + Fan + ESP32) | 12V | 28W | 18W | 1.5A (out) |
| Flight Control (Pixhawk) | 5V | 5W | 3W | 1.0A (out) |
| Servo (BEC) | 7.4V | 8W | 5W | 1.0A |
| Payload (Sensors via ESP32) | 3.3V | 6W | 5W | 0.3A |
| **TOTAL (battery-side)** | — | **~1361W** | **~155W** | **~61.3A** |

- Demo endurance: 133.2 Wh / 155W ≈ **51 min**
- Production endurance target: **5+ hours** (battery swaps)

### 1.7 Signal & Data Interconnects

| # | From | To | Gauge | Protocol | Signal | Connector |
|---|------|-----|-------|----------|--------|-----------|
| S1 | ESP32 UART1 | Pixhawk (IF-1) | 22 AWG | MAVLink UART | 3.3V TTL | JST-SH 4-pin |
| S2 | ESP32 UART2 | Jetson (IF-3) | 22 AWG | UART 115200 | 3.3V TTL | JST-SH 4-pin |
| S3 | Pixhawk PWM | ESC Signal | 22 AWG | PWM 50Hz | 3.3V logic | Servo 3-pin |
| S4 | Jetson CSI | Camera IMX219 | Ribbon | MIPI CSI-2 | LVDS diff | 15-pin FPC |
| S5 | Jetson Ethernet | Starlink Mini | Cat5e | 100BASE-T | Ethernet | RJ-45 |
| S6 | ESP32 WiFi | Other Drones | — | ESP-NOW | 2.4 GHz RF | Internal ant. |
| S8 | ESP32 UART | Atlas EZO pH | 26 AWG | UART 9600 | 3.3V TTL | CAT6 pair |
| S9 | ESP32 1-Wire | DS18B20 Temp | 26 AWG | 1-Wire | 3.3V | Waterproof |
| S10 | ESP32 Analog | TDS Conductivity | 26 AWG | Analog | 0–3.3V | DuPont 2-pin |
| S12 | ESP32 GPIO | DFRobot Ultrasonic | 26 AWG | Digital IO | 3.3V / 5V | DuPont 4-pin |

> S7 (IMU) and S11 (GPS) were removed at Rev WG-2 — Pixhawk built-in IMU and M8N GPS now serve those functions. S3 PWM source is Pixhawk (ArduPilot Rover), not ESP32 GPIO.

### 1.8 Fuse Summary (Quick Reference)

| Holder | Production | Demo | Type | Protects |
|--------|-----------|------|------|----------|
| MRBF | **100A** | **40A** (swap) | Bolt-down | Main trunk |
| MIDI | **60A** | **60A** | Bolt-down | ESC / Motor |
| ST Blade ATO | 7.5A SB | 7.5A SB | Blade | Starlink Mini (direct) |
| ST Blade ATO | 3A SB | 3A SB | Blade | 12V Buck → Jetson + Fan + ESP32 |
| ST Blade ATO | 2A SB | 2A SB | Blade | 5V Buck → Pixhawk |
| ST Blade ATO | 2A SB | 2A SB | Blade | BEC → Rudder Servo |

SB = Slow-Blow. **Four ATO branches total (down from five in Rev ISR-4).**

### 1.9 EMI Filtering (Rev ISR-4b / FAR-1)

All EMI filtering components, placement locations, and soldering instructions are documented in **AQUABOTS_EMI_FILTERING_BOM.pdf**. Summary below, updated for the FAR-1 branch consolidation.

#### Busbar-Level Bypass

| Part | Value | Placement | Notes |
|------|-------|-----------|-------|
| C1 | 1000uF / 35V Electrolytic | Across (+) and (−) busbar studs, <1" from stud centers | Absorbs low-freq transients (motor startup, ESC bursts) |
| C2 | 100nF / 50V Ceramic | In PARALLEL with C1, same studs | Absorbs high-freq hash (>1MHz). Both caps required. |

#### Per-Branch Filtering

| Branch | Input-Side Ferrite | Output-Side Cap(s) | Notes |
|--------|-------------------|---------------------|-------|
| ESC/Motor (P5) | F1: Ferrite toroid 13mm+ ID on 8 AWG (+), <2" from ESC | C3: 470uF/35V + C2: 100nF parallel at ESC input | Biggest noise source. Toroid = single pass through hole. |
| 12V Buck (P9/P18/P19/P20) | F2: Clip-on 13mm on 12 AWG (+) input | C5: 100uF/25V + C2: 100nF parallel at Jetson DC barrel; C4: 10uF/10V + C2 at ESP32 VIN; F4: clip-on 6–8mm on 22 AWG ESP32 output pair (common-mode) | Feeds the most EMI-sensitive loads (ESP32 RF, Jetson). Treat output side per-device. |
| 5V Buck (P11/P21) | F2: Clip-on 13mm on 12 AWG (+) input | C5b: 47uF/10V + C2: 100nF parallel at Pixhawk POWER connector | New branch (FAR-1). Pixhawk input needs both bulk + HF bypass because it no longer has Power Module internal filtering. |
| Starlink (P7) | F3: Clip-on 10–13mm on 12 AWG (+) | C7: 100uF/35V + C2: 100nF parallel at Starlink DC plug | Direct from busbar, no converter — needs busbar noise filtering. |
| BEC→Servo (P13/P22) | — (none needed) | C6: 100uF/16V + C2: 100nF parallel at servo connector | Servo is inductive noise source; cap at output absorbs it. |

#### Sensor Signal Filtering

| Signal | Filter | Placement |
|--------|--------|-----------|
| S10 (TDS Analog) | C2: 100nF ceramic, pin-to-GND | <0.25" from ESP32 ADC pin. **CRITICAL** — analog most vulnerable to ESC noise. |
| S8 (pH UART) | None required at 9600 baud. Add clip-on ferrite on CAT6 at ESP32 end if pool test shows noise. | ESP32 end of CAT6 breakout |
| S9 (1-Wire) | C2: 100nF ceramic, pin-to-GND (optional) | <0.5" from ESP32 pin. |

**Key rules:** Parallel caps = electrolytic + ceramic on same solder points. Ferrite clip-ons go on (+) wire only (except F4 output which takes both wires for common-mode). All leads as short as possible. Secure everything with zip ties for marine vibration.

---

## 2. CHANGELOG

### Rev FAR-1 (04-12-2026) — Converter Consolidation

**Architecture change driven by parts-count reduction and addressing mentor ISR action item (wire/fuse coordination):**

1. **ESP32 moved off its own 5V buck branch onto the 12V buck rail alongside Jetson + fan.**
   - Old: Busbar → ATO 1A → 12 AWG → dedicated 5V buck → ESP32 (22 AWG, 5V).
   - New: Busbar → ATO 3A → 12 AWG → 12V buck → { Jetson, fan, ESP32 VIN }. ESP32 breakout uses its onboard regulator to drop 12V → 3.3V.
   - Rationale: one fewer buck, one fewer fuse, one fewer branch pair. Load is well within 12V buck capacity.

2. **5V Power Module (Pixhawk POWER port brick) replaced with a generic 5V buck.**
   - Old: Busbar → ATO 2A → 12 AWG → Pixhawk 5V Power Module → Pixhawk POWER.
   - New: Busbar → ATO 2A → 12 AWG → 5V Buck → Pixhawk POWER (DF13 6-pin).
   - Repurposes the 5V buck that previously fed the ESP32. The 5V Power Module is removed from the BOM.
   - Tradeoff: no analog battery V/I telemetry into the Pixhawk POWER ADC. Acceptable for the FAR mission profile. If battery monitoring over MAVLink is later required, add a sense line to a spare ADC channel or revert to a Power Module on this branch.

3. **Fuse coordination preserved on every branch.**
   - 12V buck input: 0.9A peak < ATO 3A < 41A (12 AWG). 3.4× margin + startup inrush headroom.
   - 5V buck input: 0.15A peak < ATO 2A < 41A. Margin dominated by startup inrush allowance.

4. **EMI filtering updated.**
   - Removed: input ferrite on separate ESP32 5V buck branch.
   - Added: bulk + HF bypass caps at Pixhawk POWER input (no longer covered by Power Module internal filtering).
   - All other ferrites / caps unchanged.

### Rev ISR-4 (03-04-2026) — EMI Filtering Addition

**Added EMI filtering across all power branches and critical signal lines:**

1. **Busbar bypass caps: 1000uF/35V electrolytic + 100nF ceramic in parallel**
   - Placed across (+) and (−) busbar studs to absorb low- and high-frequency transients.
   - Single most important EMI mitigation — catches ESC-generated noise at the source bus.

2. **ESC/Motor branch: Ferrite toroid + parallel caps at ESC input**
   - Ferrite toroid (13mm+ ID, mix 31/43) on 8 AWG (+) lead, single pass, within 2" of ESC.
   - 470uF/35V low-ESR electrolytic + 100nF ceramic in parallel at ESC power input terminals.

3. **Per-branch input ferrites + output bypass caps on compute / comms rails.**

4. **Sensor signal filtering**
   - 100nF ceramic cap pin-to-GND on TDS analog input (S10) — CRITICAL for ADC accuracy.

**Documentation:** Full BOM with placement instructions in AQUABOTS_EMI_FILTERING_BOM.pdf.
**Estimated cost:** ~$22-25 for all filtering components.

### Rev ISR-3 (03-04-2026) — Fuse Coordination Audit + Wire Corrections

**Critical fixes:**

1. **Motor branch wire gauge corrected: 12 AWG → 8 AWG**
   - 12 AWG (41A rated) cannot safely carry 54A motor max draw. 8 AWG (73A) provides proper headroom.
   - Both (+) and (−) standardized to 8 AWG for motor branch.

2. **Motor fuse downsized: MIDI 125A → MIDI 60A**
   - 125A fuse on 12 AWG wire was a critical fuse coordination failure (fuse > wire ampacity).
   - 60A fuse properly coordinates: 54A load < 60A fuse < 73A wire (8 AWG).

3. **Main trunk fuse downsized: MRBF 150A → MRBF 100A (production)**
   - 150A exceeded 4 AWG wire ampacity (135A). Fuse would not protect wire in a dead short.
   - 100A properly coordinates: 61.3A load < 100A fuse < 135A wire (4 AWG).

4. **Demo trunk fuse adjusted: MRBF 50A → MRBF 40A**
   - 50A fuse on 10–12 AWG pigtail (41–55A) was marginal. 40A ensures wire protection.
   - 40A also acts as safety governor — prevents sustained full-throttle on 6Ah LiPo.

5. **Pixhawk branch fuse: ATO 1A → ATO 2A SB**
   - 1A was tight for Pixhawk power module inrush. 2A provides margin.

6. **Jetson branch fuse: ATO 7.5A → ATO 3A SB**
   - 7.5A was 6× the 1.26A max load. 3A provides tighter fault protection.

7. **Low-current branch wires upgraded: 18 AWG → 12 AWG**
   - Production marine durability and wire inventory standardization.

8. **Starlink connection clarified: Direct from busbar (no converter)**
   - Starlink Mini accepts 12–48V DC. Both 22.2V (demo) and 25.6V (prod) are in range.

### Rev ISR-2 (03-04-2026) — Dual Configuration Design

- Added production (LiTime LiFePO4) / demo (Ovonic LiPo) dual-config concept.
- Designed XT90 adapter pigtail for demo battery connection.
- Established "build once for production, adapt for demo" principle.

### Rev ISR (2026-02-xx) — ISR Presentation

- Main fuse upgraded: 80A → 150A (MRBF holder).
- Added dedicated 125A motor fuse (MIDI block).
- Added proper fuse blocks: MRBF + MIDI + ST Blade ATO.
- Added thermal pads for heat management.
- All parts ordered ($417 total).

### Rev CDR (2025-12-xx) — Major Simplification

- Switched from 24V LiFePO4 to 6S LiPo (22.2V).
- Eliminated 48V boost converter and PoE injector.
- Eliminated BMS.
- Starlink Mini powered directly from battery rail.

### Rev PDR (2025-10-xx) — Original Design

- 24V LiFePO4 with BMS.
- 48V boost converter + PoE for Starlink.
- 19V buck converter.
- Complex power chain (deprecated).

---

## 3. PARTS LIST — WHAT TO ORDER / SWAP

### Fuse Elements to Order (replacing previously ordered items)

| Part | Replaces | Qty | Est. Price |
|------|----------|-----|------------|
| MRBF 100A fuse element | MRBF 150A (ordered) | 1 | ~$8 |
| MRBF 40A fuse element | (new for demo) | 1 | ~$8 |
| MIDI 60A fuse element | MIDI 125A (ordered) | 1 | ~$6 |
| ATO 2A slow-blow | ATO 1A (old ESP32 branch element, now repurposed for 5V buck / Pixhawk) | 1 | ~$2 |
| ATO 3A slow-blow | ATO 7.5A (old Jetson branch) | 1 | ~$2 |

### Wire to Order

| Item | Qty | Notes |
|------|-----|-------|
| 8 AWG Red silicone wire | 2 ft | ESC (+) branch |
| 8 AWG Black silicone wire | 2 ft | ESC (−) branch |
| 12 AWG Red (if not already stocked) | 3 ft | Consolidated branches |
| 12 AWG Black (if not already stocked) | 3 ft | Consolidated branches |

### Ring Terminals to Order

| Size | For | Qty |
|------|-----|-----|
| 8 AWG ring, 1/4" stud | ESC branch to busbar | 2 |
| 8 AWG ring, MIDI blade | ESC branch to MIDI holder | 1 |

### Removed from BOM (FAR-1)

- Dedicated 5V Power Module for Pixhawk POWER port — replaced with repurposed 5V buck.
- One extra ATO fuse branch (ESP32 now on 12V buck rail).

### Existing Parts (No Change)

- MRBF fuse holder — keep (just swap element)
- MIDI fuse block — keep (just swap element)
- ST Blade ATO fuse block — keep
- Bus bars (+/−) — keep
- Kill switch — keep
- Castle BEC — keep
- Both buck converters — keep (5V now routed to Pixhawk, 12V now adds ESP32)
- All connectors — keep

### EMI Filtering Parts to Order (Rev ISR-4 / FAR-1)

| Part | Value / Spec | Qty | Est. Price | Location |
|------|-------------|-----|------------|----------|
| Electrolytic cap | 1000uF / 35V radial | 1 | ~$2 | Busbar bypass |
| Electrolytic cap | 470uF / 35V low-ESR radial | 1 | ~$2 | ESC input |
| Electrolytic cap | 100uF / 35V radial | 1 | ~$1 | Starlink DC input |
| Electrolytic cap | 100uF / 25V radial | 1 | ~$1 | Jetson DC barrel |
| Electrolytic cap | 47uF / 10V radial | 1 | ~$0.50 | Pixhawk POWER input (NEW, FAR-1) |
| Electrolytic cap | 100uF / 16V radial | 1 | ~$1 | BEC/servo output |
| Electrolytic cap | 10uF / 10V radial | 1 | ~$0.50 | ESP32 VIN |
| Ceramic disc/MLCC cap | 100nF (0.1uF) / 50V | 10+ pack | ~$3 | Multiple (parallel with every electrolytic + sensor pins) |
| Ferrite toroid | 13mm+ ID, mix 31/43 | 1 | ~$3 | ESC 8 AWG (+) lead |
| Clip-on ferrite | 13mm ID (fits 12 AWG) | 2 | ~$4 | 12V Buck input, 5V Buck input |
| Clip-on ferrite | 10–13mm ID (fits 12–16 AWG) | 1 | ~$2 | Starlink (+) input lead |
| Clip-on ferrite | 6–8mm ID (fits 22 AWG) | 1 | ~$2 | 12V Buck → ESP32 output |

**EMI filtering subtotal: ~$22–25**

---

## 4. ASSEMBLY NOTES

### Safety-First Sequence

1. **Verify all connections are de-energized** before starting.
2. Build the trunk FIRST: MRBF holder → Kill Switch → (+) Busbar.
3. Connect (−) Busbar run.
4. **Install busbar bypass caps:** Solder C1 (1000uF/35V) + C2 (100nF) in parallel across (+) and (−) busbar studs. Leads <1". Secure with zip tie.
5. Install branch fuses in ST Blade ATO block (but leave main MRBF and MIDI empty).
6. Wire all branch circuits from busbars to converters/loads.
7. **Install input-side ferrites:** F1 toroid on ESC 8 AWG (+), F2 clip-ons on 5V Buck and 12V Buck 12 AWG (+) inputs, F3 clip-on on Starlink 12 AWG (+).
8. Wire all load-side connections (converters → devices). Note that 12V buck splits three ways: Jetson barrel, fan JST, ESP32 VIN terminal.
9. **Install output-side ferrite:** F4 clip-on on 12V Buck → ESP32 22 AWG pair.
10. **Install all output-side parallel caps:** C3+C2 at ESC, C4+C2 at ESP32 VIN, C5+C2 at Jetson, C5b+C2 at Pixhawk POWER, C6+C2 at servo, C7+C2 at Starlink. Observe electrolytic polarity.
11. **Install sensor signal filtering:** C2 on TDS analog pin (S10). No beads on pH UART unless pool test requires it.
12. **Final inspection:** Check every terminal for tightness, correct polarity, no stray strands. Verify no shorts introduced by cap leads.
13. Insert MIDI 60A fuse element.
14. Insert MRBF fuse element LAST (this energizes the system).
15. Test with multimeter at each load point before powering devices.

### Demo vs Production Switchover

**To switch from production → demo:**
1. Remove MRBF fuse element (de-energize system).
2. Disconnect 4 AWG trunk leads from battery M8 posts.
3. Connect XT90 adapter pigtail ring terminals to MRBF input stud and (−) busbar.
4. Insert MRBF 40A fuse element.
5. Plug Ovonic LiPo XT90 into adapter pigtail.

**To switch from demo → production:**
1. Remove MRBF fuse element (de-energize system).
2. Disconnect adapter pigtail from MRBF stud and busbar.
3. Bolt 4 AWG trunk ring terminals to LiTime M8 posts.
4. Insert MRBF 100A fuse element.

---

## 5. KNOWN ISSUES & FUTURE WORK

- [ ] Verify Starlink Mini DC input connector type — may need custom DC pigtail from ATO fuse block output to Starlink's proprietary power connector.
- [ ] Measure actual motor inrush current during pool testing — confirm 60A MIDI doesn't nuisance-trip on startup. If it does, consider 70A MIDI.
- [ ] Measure actual Jetson boot-up inrush plus ESP32 startup on the consolidated 12V rail — confirm 3A ATO doesn't nuisance-trip.
- [ ] Perform full-load voltage drop test across busbars under 54A motor draw.
- [ ] Add waterproofing / conformal coating plan for marine environment.
- [ ] Document LiTime battery mounting and M8 terminal torque specs.
- [ ] Verify ESP-NOW RF performance after EMI filtering installation — check RSSI and packet loss vs. pre-filter baseline.
- [ ] Test TDS analog sensor accuracy with motor running at cruise — compare with/without 100nF cap on ADC pin.
- [ ] Confirm Pixhawk boots cleanly from the generic 5V buck (no brownout on ESC calibration inrush). If brownouts observed, add series Schottky or larger input bulk cap at Pixhawk POWER.
- [ ] If battery monitoring over MAVLink is required, wire a V/I sense line to a spare Pixhawk ADC channel or revert the Pixhawk branch to a dedicated Power Module.
