# AQUABOTS Power System — Master Reference & Changelog

**Team 26061 | ENGR 498B Spring 2026**
**Owner:** John (Software Integration Lead / Power System Design)
**Last Updated:** 2026-03-04 (Rev ISR-4)

---

## 1. CURRENT CONFIGURATION (Rev ISR-3)

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
| P7/P8 | Starlink (direct) | Busbar | Starlink Mini | 16 AWG | 16 AWG | ATO 7.5A SB | 4.7A | 70W |
| P9/P10 | 5V Pwr Mod→Pixhawk | Busbar | 5V Pwr Module | 18 AWG | 18 AWG | ATO 2A SB | ~0.5A | ~2W |
| P11/P12 | 12V Buck→Jetson+Fan | Busbar | 12V Buck | 18 AWG | 18 AWG | ATO 3A SB | 1.26A | 15W |
| P13/P14 | 5V Buck→ESP32 | Busbar | 5V Buck | **12 AWG** | **12 AWG** | ATO 1A SB | 0.23A | 5W |
| P15/P16 | BEC→Servo | Busbar | BEC (Castle) | **12 AWG** | **12 AWG** | ATO 2A SB | 1.0A | 5W |

**Starlink note:** NO converter in path. Starlink Mini accepts 12–48V DC directly. Both 22.2V (demo) and 25.6V (prod) are in range.

### 1.4 Load-Side Connections (Converter → Device)

| # | From | To | Gauge | ~Length | Connector |
|---|------|-----|-------|--------|-----------|
| P17 | ESC (3-phase) | Motor (Apisqueen 5080) | 8 AWG | 10" | Bullet 4mm |
| P18 | 5V Power Module | Pixhawk 4X FC | 22 AWG | 4" | DF13 6-pin |
| P19 | 12V Buck | Jetson Orin Nano | 18 AWG | 6" | DC barrel |
| P20 | 12V Buck | Cooling Fan | 22 AWG | 4" | JST 2-pin |
| P21 | 5V Buck | ESP32-S3 | 22 AWG | 4" | USB-C / pin hdr |
| P22 | BEC (Castle) | Rudder Servo | 22 AWG | 8" | Servo 3-pin |
| P23 | ESP32 3.3V reg | Sensors (all) | 26 AWG | varies | DuPont / JST |
| P24 | Jetson 3.3V reg | Camera (IMX219) | Ribbon | 3" | 15-pin FPC |

### 1.5 Fuse Coordination Verification

Every branch passes: **Max Load < Fuse Rating < Wire Ampacity**

| Branch | Max Load | Fuse | Wire | Wire Ampacity | ✅ |
|--------|----------|------|------|---------------|---|
| Trunk (prod) | 61.3A | 100A | 4 AWG | 135A | PASS |
| Trunk (demo) | 40A (governed) | 40A | 10–12 AWG | 41–55A | PASS |
| ESC/Motor | 54A | 60A | 8 AWG | 73A | PASS |
| Starlink | 4.7A | 7.5A | 16 AWG | 22A | PASS |
| Pixhawk | ~0.5A | 2A | 18 AWG | 16A | PASS |
| Jetson+Fan | 1.26A | 3A | 18 AWG | 16A | PASS |
| ESP32 | 0.23A | 1A | 12 AWG | 41A | PASS |
| BEC/Servo | 1.0A | 2A | 12 AWG | 41A | PASS |

### 1.6 Power Budget

| Subsystem | Voltage | Max Power | Cruise Power | Max Current |
|-----------|---------|-----------|-------------|-------------|
| Propulsion (Motor) | 22–26V | 1200W | 60W | 54.0A |
| Comms (Starlink) | 22–26V direct | 105W | 70W | 4.7A |
| Compute (Jetson+Fan) | 12V | 28W | 15W | 1.3A |
| Control (ESP32+Servo) | 5V / 7.4V | 22W | 5W | 1.0A |
| Payload (Sensors) | 3.3V | 6W | 5W | 0.3A |
| **TOTAL** | — | **~1361W** | **~155W** | **~61.3A** |

- Demo endurance: 133.2 Wh / 155W ≈ **51 min**
- Production endurance target: **5+ hours** (battery swaps)

### 1.7 Signal & Data Interconnects

| # | From | To | Gauge | Protocol | Signal | Connector |
|---|------|-----|-------|----------|--------|-----------|
| S1 | ESP32 UART1 | Pixhawk (IF-1) | 22 AWG | MAVLink UART | 3.3V TTL | JST-SH 4-pin |
| S2 | ESP32 UART2 | Jetson (IF-3) | 22 AWG | UART 115200 | 3.3V TTL | JST-SH 4-pin |
| S3 | ESP32 GPIO | ESC Signal | 22 AWG | PWM 50Hz | 3.3V logic | Servo 3-pin |
| S4 | Jetson CSI | Camera IMX219 | Ribbon | MIPI CSI-2 | LVDS diff | 15-pin FPC |
| S5 | Jetson Ethernet | Starlink Mini | Cat5e | 100BASE-T | Ethernet | RJ-45 |
| S6 | ESP32 WiFi | Other Drones | — | ESP-NOW | 2.4 GHz RF | Internal ant. |
| S7 | ESP32 I2C | MPU6050 IMU | 26 AWG | I2C | 3.3V | DuPont 4-pin |
| S8 | ESP32 I2C | Atlas pH Circuit | 26 AWG | I2C / UART | 3.3V | DuPont + BNC |
| S9 | ESP32 1-Wire | DS18B20 Temp | 26 AWG | 1-Wire | 3.3V | Waterproof |
| S10 | ESP32 Analog | TDS Conductivity | 26 AWG | Analog | 0–3.3V | DuPont 2-pin |
| S11 | ESP32 UART | GPS Module | 26 AWG | UART 9600 | 3.3V TTL | DuPont 4-pin |
| S12 | ESP32 GPIO | DFRobot Ultrasonic | 26 AWG | Digital IO | 3.3V / 5V | DuPont 4-pin |

### 1.8 Fuse Summary (Quick Reference)

| Holder | Production | Demo | Type | Protects |
|--------|-----------|------|------|----------|
| MRBF | **100A** | **40A** (swap) | Bolt-down | Main trunk |
| MIDI | **60A** | **60A** | Bolt-down | ESC / Motor |
| ST Blade ATO | 7.5A SB | 7.5A SB | Blade | Starlink Mini (direct) |
| ST Blade ATO | 2A SB | 2A SB | Blade | 5V Pwr Mod → Pixhawk |
| ST Blade ATO | 3A SB | 3A SB | Blade | 12V Buck → Jetson + Fan |
| ST Blade ATO | 1A SB | 1A SB | Blade | 5V Buck → ESP32 |
| ST Blade ATO | 2A SB | 2A SB | Blade | BEC → Rudder Servo |

SB = Slow-Blow

### 1.9 EMI Filtering (Rev ISR-4)

All EMI filtering components, placement locations, and soldering instructions are documented in **AQUABOTS_EMI_FILTERING_BOM.pdf**. Summary below:

#### Busbar-Level Bypass

| Part | Value | Placement | Notes |
|------|-------|-----------|-------|
| C1 | 1000uF / 35V Electrolytic | Across (+) and (−) busbar studs, <1" from stud centers | Absorbs low-freq transients (motor startup, ESC bursts) |
| C2 | 100nF / 50V Ceramic | In PARALLEL with C1, same studs | Absorbs high-freq hash (>1MHz). Both caps required. |

#### Per-Branch Filtering

| Branch | Input-Side Ferrite | Output-Side Cap(s) | Notes |
|--------|-------------------|---------------------|-------|
| ESC/Motor (P5) | F1: Ferrite toroid 13mm+ ID on 8 AWG (+), <2" from ESC | C3: 470uF/35V + C2: 100nF parallel at ESC input | Biggest noise source. Toroid = single pass through hole. |
| 5V Buck→ESP32 (P13/P21) | F2: Clip-on 13mm on 12 AWG (+) input | F4: Clip-on 6-8mm on 22AWG output pair; C4: 10uF/10V + C2: 100nF parallel at ESP32 VIN | Most sensitive branch. Both input AND output filtering. |
| 12V Buck→Jetson (P11/P19) | F2: Clip-on 13mm on 12 AWG (+) input | C5: 100uF/25V + C2: 100nF parallel at Jetson DC barrel | Jetson has onboard regulation but needs clean input. |
| Starlink (P7) | F3: Clip-on 10-13mm on 12 AWG (+) | C7: 100uF/35V + C2: 100nF parallel at Starlink DC plug | Direct from busbar, no converter — needs busbar noise filtering. |
| BEC→Servo (P15/P22) | — (none needed) | C6: 100uF/16V + C2: 100nF parallel at servo connector | Servo is inductive noise source; cap at output absorbs it. |
| Pixhawk (P9) | — (none needed) | — (Pixhawk power module has internal filtering) | Lowest-current branch, well-isolated by 5V power module. |

#### Sensor Signal Filtering

| Signal | Filter | Placement |
|--------|--------|-----------|
| S10 (TDS Analog) | C2: 100nF ceramic, pin-to-GND | <0.25" from ESP32 ADC pin. **CRITICAL** — analog most vulnerable to ESC noise. |
| S7 (IMU I2C) | F5: 600Ω@100MHz ferrite bead inline on SDA and SCL | <1" from ESP32 I2C pins. Cut wire, solder bead in series. |
| S8 (pH I2C) | F5: 600Ω@100MHz ferrite bead inline on SDA and SCL | <1" from ESP32 I2C pins. Same type as S7. |
| S9 (1-Wire) | C2: 100nF ceramic, pin-to-GND (optional) | <0.5" from ESP32 pin. Lower priority than S10/S7/S8. |
| S11 (GPS UART) | C2: 100nF ceramic, pin-to-GND (optional) | <0.5" from ESP32 pin. Lower priority. |

**Key rules:** Parallel caps = electrolytic + ceramic on same solder points. Ferrite clip-ons go on (+) wire only (except F4 output which takes both wires for common-mode). All leads as short as possible. Secure everything with zip ties for marine vibration.

---

## 2. CHANGELOG

### Rev ISR-4 (2026-03-04) — EMI Filtering Addition

**Added EMI filtering across all power branches and critical signal lines:**

1. **Busbar bypass caps: 1000uF/35V electrolytic + 100nF ceramic in parallel**
   - Placed across (+) and (−) busbar studs to absorb low- and high-frequency transients.
   - This is the single most important EMI mitigation — catches ESC-generated noise at the source bus.

2. **ESC/Motor branch: Ferrite toroid + parallel caps at ESC input**
   - Ferrite toroid (13mm+ ID, mix 31/43) on 8 AWG (+) lead, single pass, within 2" of ESC.
   - 470uF/35V low-ESR electrolytic + 100nF ceramic in parallel at ESC power input terminals.

3. **5V Buck→ESP32 branch: Dual-stage filtering (input + output)**
   - Input: Clip-on ferrite on 12 AWG (+) lead, within 2" of buck input.
   - Output: Clip-on ferrite on 22 AWG pair (both wires, common-mode), within 2" of ESP32.
   - 10uF/10V electrolytic + 100nF ceramic in parallel at ESP32 VIN pins.
   - Rationale: ESP32 2.4GHz RF and analog ADC inputs are the most EMI-sensitive loads.

4. **12V Buck→Jetson branch: Input ferrite + output caps**
   - Clip-on ferrite on 12 AWG (+) input lead.
   - 100uF/25V electrolytic + 100nF ceramic in parallel at Jetson DC barrel.

5. **Starlink branch: Input ferrite + output caps**
   - Clip-on ferrite on 12 AWG (+) lead after ATO fuse.
   - 100uF/35V electrolytic + 100nF ceramic at Starlink DC input connector.

6. **BEC→Servo branch: Output caps only**
   - 100uF/16V electrolytic + 100nF ceramic at servo connector output.

7. **Sensor signal filtering**
   - 100nF ceramic cap pin-to-GND on TDS analog input (S10) — CRITICAL for ADC accuracy.
   - 600Ω@100MHz ferrite beads inline on I2C SDA/SCL for IMU (S7) and pH (S8) — 4 beads total.
   - Optional 100nF caps on 1-Wire (S9) and GPS UART (S11) signal pins.

**Documentation:** Full BOM with placement instructions in AQUABOTS_EMI_FILTERING_BOM.pdf.
**Estimated cost:** ~$22-25 for all filtering components.
**Wiring diagram updated:** AQUABOTS_WIRING_DIAGRAM.html now shows all EMI components (Rev ISR-4).

### Rev ISR-3 (2026-03-04) — Fuse Coordination Audit + Wire Corrections

**Critical fixes:**

1. **Motor branch wire gauge corrected: 12 AWG → 8 AWG**
   - Root cause: ISR slide 27 showed 8 AWG Red / 10 AWG Blk to ESC. Project summary incorrectly stated "12 AWG (upgraded from 8/10 AWG)" — the ISR judge's "upgrade to 12 AWG" was for non-motor branches (from 14 AWG), NOT the motor branch.
   - 12 AWG (41A rated) cannot safely carry 54A motor max draw. 8 AWG (73A) provides proper headroom.
   - Both (+) and (−) standardized to 8 AWG for motor branch.

2. **Motor fuse downsized: MIDI 125A → MIDI 60A**
   - 125A fuse on 12 AWG wire was a critical fuse coordination failure (fuse > wire ampacity).
   - 60A fuse properly coordinates: 54A load < 60A fuse < 73A wire (8 AWG).
   - 60A slow-blow MIDI handles motor startup inrush without nuisance tripping.

3. **Main trunk fuse downsized: MRBF 150A → MRBF 100A (production)**
   - 150A exceeded 4 AWG wire ampacity (135A). Fuse would not protect wire in a dead short.
   - 100A properly coordinates: 61.3A load < 100A fuse < 135A wire (4 AWG).

4. **Demo trunk fuse adjusted: MRBF 50A → MRBF 40A**
   - 50A fuse on 10–12 AWG pigtail (41–55A) was marginal. 40A ensures wire protection.
   - 40A also acts as safety governor — prevents sustained full-throttle on 6Ah LiPo.

**Minor improvements:**

5. **Pixhawk branch fuse: ATO 1A → ATO 2A SB**
   - 1A was tight for Pixhawk power module inrush. 2A provides margin.

6. **Jetson branch fuse: ATO 7.5A → ATO 3A SB**
   - 7.5A was 6× the 1.26A max load. 3A provides tighter fault protection.

7. **5V Buck→ESP32 wire upgraded: 18 AWG → 12 AWG**
   - Per John's request for production marine durability and wire inventory standardization.

8. **BEC→Servo wire upgraded: 18 AWG → 12 AWG**
   - Same rationale as above.

9. **Starlink connection clarified: Direct from busbar (no converter)**
   - Starlink Mini accepts 12–48V DC. Both 22.2V (demo) and 25.6V (prod) are in range.
   - Path: (+) Busbar → ATO 7.5A SB → Starlink Mini. No voltage conversion.

### Rev ISR-2 (2026-03-04) — Dual Configuration Design

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
| ATO 2A slow-blow | ATO 1A (Pixhawk branch) | 1 | ~$2 |
| ATO 3A slow-blow | ATO 7.5A (Jetson branch) | 1 | ~$2 |

### Wire to Order

| Item | Qty | Notes |
|------|-----|-------|
| 8 AWG Red silicone wire | 2 ft | ESC (+) branch |
| 8 AWG Black silicone wire | 2 ft | ESC (−) branch |
| 12 AWG Red (if not already stocked) | 3 ft | 5V Buck + BEC branches |
| 12 AWG Black (if not already stocked) | 3 ft | 5V Buck + BEC branches |

### Ring Terminals to Order

| Size | For | Qty |
|------|-----|-----|
| 8 AWG ring, 1/4" stud | ESC branch to busbar | 2 |
| 8 AWG ring, MIDI blade | ESC branch to MIDI holder | 1 |

### Existing Parts (No Change)

- MRBF fuse holder — keep (just swap element)
- MIDI fuse block — keep (just swap element)
- ST Blade ATO fuse block — keep
- Bus bars (+/−) — keep
- Kill switch — keep
- Castle BEC — keep
- All buck converters — keep
- All connectors — keep

### EMI Filtering Parts to Order (Rev ISR-4)

| Part | Value / Spec | Qty | Est. Price | Location |
|------|-------------|-----|------------|----------|
| Electrolytic cap | 1000uF / 35V radial | 1 | ~$2 | Busbar bypass |
| Electrolytic cap | 470uF / 35V low-ESR radial | 1 | ~$2 | ESC input |
| Electrolytic cap | 100uF / 35V radial | 1 | ~$1 | Starlink DC input |
| Electrolytic cap | 100uF / 25V radial | 1 | ~$1 | Jetson DC barrel |
| Electrolytic cap | 100uF / 16V radial | 1 | ~$1 | BEC/servo output |
| Electrolytic cap | 10uF / 10V radial | 1 | ~$0.50 | ESP32 VIN |
| Ceramic disc/MLCC cap | 100nF (0.1uF) / 50V | 10+ pack | ~$3 | Multiple (parallel with every electrolytic + sensor pins) |
| Ferrite toroid | 13mm+ ID, mix 31/43 | 1 | ~$3 | ESC 8 AWG (+) lead |
| Clip-on ferrite | 13mm ID (fits 12 AWG) | 2 | ~$4 | 5V Buck input, 12V Buck input |
| Clip-on ferrite | 10–13mm ID (fits 12–16 AWG) | 1 | ~$2 | Starlink (+) input lead |
| Clip-on ferrite | 6–8mm ID (fits 22 AWG) | 1 | ~$2 | 5V Buck output → ESP32 |
| Ferrite bead (thru-hole) | 600Ω @ 100MHz | 4–6 | ~$2 | I2C SDA/SCL lines, optional UART |

**EMI filtering subtotal: ~$22–25**

---

## 4. ASSEMBLY NOTES

### Safety-First Sequence

1. **Verify all connections are de-energized** before starting.
2. Build the trunk FIRST: MRBF holder → Kill Switch → (+) Busbar.
3. Connect (−) Busbar run.
4. **Install busbar bypass caps (E1):** Solder C1 (1000uF/35V) + C2 (100nF) in parallel across (+) and (−) busbar studs. Leads <1". Secure with zip tie.
5. Install branch fuses in ST Blade ATO block (but leave main MRBF and MIDI empty).
6. Wire all branch circuits from busbars to converters/loads.
7. **Install input-side ferrites:** F1 toroid on ESC 8 AWG (+), F2 clip-ons on 5V Buck and 12V Buck 12 AWG (+) inputs, F3 clip-on on Starlink 12 AWG (+).
8. Wire all load-side connections (converters → devices).
9. **Install output-side ferrite:** F4 clip-on on 5V Buck → ESP32 22 AWG pair.
10. **Install all output-side parallel caps:** C3+C2 at ESC, C4+C2 at ESP32, C5+C2 at Jetson, C6+C2 at servo, C7+C2 at Starlink. Observe electrolytic polarity.
11. **Install sensor signal filtering:** C2 on TDS analog pin (S10), ferrite beads inline on I2C SDA/SCL (S7, S8).
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
- [ ] Measure actual Jetson boot-up inrush — confirm 3A ATO doesn't nuisance-trip.
- [ ] Perform full-load voltage drop test across busbars under 54A motor draw.
- [ ] Add waterproofing / conformal coating plan for marine environment.
- [ ] Document LiTime battery mounting and M8 terminal torque specs.
- [ ] Verify ESP-NOW RF performance after EMI filtering installation — check RSSI and packet loss vs. pre-filter baseline.
- [ ] Test TDS analog sensor accuracy with motor running at cruise — compare with/without 100nF cap on ADC pin.
- [ ] Consider adding 100nF caps to ESP32 UART lines (S1 MAVLink, S2 Jetson) if communication errors observed during motor operation.
