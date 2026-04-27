---
title: "AQUABOTS EMI Install Procedure"
subtitle: "Team 26061 · ENGR 498B Spring 2026 · Rev FAR-1 / WG-3 unified"
author: "Owner: John"
date: "2026-04-26"
geometry: "margin=0.7in"
fontsize: 10pt
---

# AQUABOTS EMI Install Procedure

**Team 26061 | Rev FAR-1 / WG-3 unified | 2026-04-26**

Single-document EMI install procedure for the AQUABOTS hull. Supersedes the prior `AQUABOTS_EMI_INSTALL_GUIDE.md` (Rev WG-3 / FAR-1) and `EMI_FILTERING_INSTALL_CHECKLIST.md` (FAR-1 patched). Pinouts and wire IDs match `AQUABOTS_WIRING_GUIDE.md` Rev WG-3. Where this procedure deviates from `AQUABOTS_EMI_FILTERING_BOM.pdf` Rev ISR-4b, the deviations table at the end gives the reasons.

**Goal:** Physically install all EMI filtering (caps, ferrites, copper tape, plate ground) on the FAR-1 / WG-3 topology. Required before extended motor testing or any auto-mode water test — motor EMF will destroy compass/GPS data otherwise.

**Estimated time:** 2–3 hours (soldering + per-section continuity checks + shielding). Add ~45 min for the aluminum plate shielding sub-procedure if doing it in the same session.

**This document is the single source of truth for the install. Do not flip back to the predecessor docs — they have been stubbed.**

---

## 0 — Pre-Install Supply Gathering (READ FIRST)

Pull every part on this list onto the bench before unscrewing anything. Sections 0.1–0.4 are the complete shopping/staging list.

### 0.1 Components — caps, ferrites, beads

Quantities reflect FAR-1 reality (C5b added; F4 on P20; C4 = 25V+; F5 beads zero up-front, optional pool-test-gated). Cross-checked against BOM Rev ISR-4b — see "Known Deviations from BOM" at the end.

| ID  | Value / rating                       | Qty | Where it goes                                       |
|-----|--------------------------------------|-----|-----------------------------------------------------|
| C1  | 1000 µF / 35 V+ electrolytic         | 1   | Busbar (+)/(−) studs (§1)                           |
| C2  | 100 nF / 50 V+ ceramic disc          | ~9  | Busbar; ESC; ESP32 VIN; Jetson barrel; Pixhawk POWER; Starlink; servo; TDS ADC; (+1 optional 1-Wire) |
| C3  | 470 µF / 35 V+ **LOW-ESR** electrolytic | 1   | ESC (+)/(−) input terminals (§2)                  |
| C4  | 10 µF / **25 V+** electrolytic       | 1   | ESP32 VIN / GND, <0.5" from header (§5) — **25 V+ minimum, ESP32 VIN is 12 V post-FAR-1** |
| C5  | 100 µF / 25–50 V electrolytic        | 1   | Jetson DC barrel (§5)                               |
| C5b | 47 µF / 10 V+ electrolytic           | 1   | Pixhawk POWER DF13 +5V/GND (§6) — **NEW under FAR-1** |
| C6  | 100 µF / 16–50 V electrolytic        | 1   | Servo 3-pin connector (§8)                          |
| C7  | 100 µF / 35–50 V electrolytic        | 1   | Starlink DC plug (§7)                               |
| F1  | Hondark MnZn ferrite toroid 38×19×13 mm | 1 | P5 (8 AWG +) at ESC end, single pass (§2)         |
| F2  | Raogoodcx 13 mm clip-on ferrite      | 2   | P9 (12V buck input) + P11 (5V buck input) (§3, §4) |
| F3  | Raogoodcx 13 mm clip-on ferrite      | 1   | P7 (Starlink +) at fuse end (§7)                    |
| F4  | Raogoodcx 6–13 mm clip-on ferrite    | 1   | P20 (12V buck → ESP32 pair, BOTH wires, common-mode) (§5) |
| F5  | BOJACK ~70 Ω @ 100 MHz axial bead    | **0** | **Optional / pool-test-gated.** pH is UART, not I²C — do NOT cut/splice F5 beads up-front. If pool-test reveals UART framing errors with motor on, retrofit a single CAT6 clip-on at the ESP32 end. (§9) |

### 0.2 Wire, cable, shield, hardware

| Item                                        | Spec / size                          | Approx qty           |
|---------------------------------------------|--------------------------------------|----------------------|
| Copper foil tape (conductive adhesive) — SH1 | 1" wide                              | ~1 roll (10+ ft used: P20 cable + S1 cable + 4 component bodies) |
| Automotive self-adhesion (electrical) tape — SH2 | Standard                          | 1 roll               |
| Split loom — SH3                            | 1/4" and 3/8" ID                     | as needed            |
| Heat shrink                                 | Assorted (1/16"–1/2")                | full assortment      |
| Drain wire pigtails                         | 22–26 AWG, ~2" each                  | 6 (one per shield)   |
| Ring terminals                              | SC (M5/M6) for busbar studs          | 2 (for C1 leads)     |
| Zip ties                                    | Small                                | ~25                  |
| Kapton tape (plate prep — §11 only)         | 2" wide                              | 1 roll (on hand)     |
| Thermal pads (plate prep — §11 only)        | Dielectric silicone, ~50×50 mm sized to converter footprint (12V buck, 5V buck, BEC, ESC underside) | 4–5 pads (on hand) |
| 12 AWG plate ground jumper (§11 only)       | BLK, ~6"                             | 1                    |

### 0.3 Tools

- Soldering iron (35 W+) with fine + chisel tips
- Leaded solder (60/40 or 63/37) + flux pen
- Helping-hands / PCB vise
- Flush cutters
- Wire strippers (covers 26–8 AWG)
- Crimper (ring terminals)
- Multimeter — continuity beep + DC volts ranges
- Heat gun
- Tweezers
- ESD strap
- Oscilloscope (optional but useful for V5/V6 diagnostics)
- Torque wrench for busbar studs (M6/M8 — to spec, do not over-torque ring terminals)

### 0.4 Consumables

- Isopropyl alcohol (90% or higher) + lint-free wipes — clean joints before soldering, clean copper tape adhesive surface
- Kapton tape — see §11 plate prep
- Dielectric grease — for the DF13 6-pin Pixhawk POWER connector pin housing only (not on contacts)
- Thermal pads — see §11 plate prep (sized per converter footprint)

---

## 1 — Prerequisites & Safety

- [ ] Main battery **DISCONNECTED** at kill switch.
- [ ] Multimeter across busbar reads **<0.1 V**. If not, find what is back-feeding before going further.
- [ ] All converters off. No LEDs lit anywhere on the plate.
- [ ] MIDI 60 A and MRBF fuse elements **removed** (re-insert during V3 smoke test).
- [ ] ESD strap on; bench has ESD-safe surface.
- [ ] Ventilation for soldering. Leaded solder fumes are not your friend.
- [ ] This procedure document open. Predecessor `AQUABOTS_EMI_INSTALL_GUIDE.md` and `EMI_FILTERING_INSTALL_CHECKLIST.md` have been stubbed and should not be referenced.
- [ ] `AQUABOTS_WIRING_GUIDE.md` Rev WG-3 nearby for layout reference (this procedure embeds wire IDs but the wiring guide governs routing).
- [ ] BOM PDF `AQUABOTS_EMI_FILTERING_BOM.pdf` Rev ISR-4b nearby — but treat as stale. See "Known Deviations from BOM" at end of this document.

---

## 2 — Reference: Wire IDs and Pinouts (embedded so you don't flip)

FAR-1 / WG-3 power topology (four ATO branches, no dedicated 5V Power Module).

### 2.1 Wire IDs touched in this procedure

| Wire ID | Path                                    | Gauge      | Rail / signal              | Used in section |
|---------|-----------------------------------------|------------|----------------------------|-----------------|
| P5      | (+) Busbar → MIDI 60 A → ESC (+) input  | 8 AWG RED  | 22–26 V (busbar)           | §2 (ESC branch) |
| P6      | (−) Busbar → ESC (−) input              | 8 AWG BLK  | GND                        | §2              |
| P7      | (+) Busbar → ATO 7.5 A → Starlink DC (+) | 12 AWG RED | 22–26 V                    | §7 (Starlink)   |
| P8      | (−) Busbar → Starlink DC (−)            | 12 AWG BLK | GND                        | §7              |
| **P9**  | (+) Busbar → ATO 3 A → 12V buck input (+) | 12 AWG RED | 22–26 V → 12V buck       | §3 (12V buck input) |
| P10     | (−) Busbar → 12V buck input (−)         | 12 AWG BLK | GND                        | §3              |
| **P11** | (+) Busbar → ATO 2 A → 5V buck input (+) | 12 AWG RED | 22–26 V → 5V buck         | §4 (5V buck input) |
| P12     | (−) Busbar → 5V buck input (−)          | 12 AWG BLK | GND                        | §4              |
| **P13** | (+) Busbar → ATO 2 A → BEC input (+)    | 12 AWG RED | 22–26 V → BEC              | §8 (BEC/servo)  |
| P14     | (−) Busbar → BEC input (−)              | 12 AWG BLK | GND                        | §8              |
| P17     | ESC 3-phase → Motor 5080                | 8 AWG ×3   | 3-phase motor              | (do not wrap; noise source) |
| P18     | 12V buck → Jetson DC barrel             | 22 AWG pr  | 12 V                       | §5              |
| P19     | 12V buck → Cooling fan                  | 22 AWG pr  | 12 V                       | (no extra filter) |
| **P20** | 12V buck → ESP32-S3 breakout VIN        | 22 AWG pr  | **12 V** (FAR-1)           | §5 (F4 + C4 + C2); §10 (copper-tape wrap) |
| **P21** | 5V buck → Pixhawk 4X **POWER** (DF13 6-pin) | 22 AWG pr | 5.0 V                    | §6 (C5b + C2)   |
| P22     | BEC (Castle) → Rudder Servo             | 22 AWG pr  | 5.5 / 6 V (BEC spec)       | §8              |
| S1      | ESP32 UART1 → Pixhawk (MAVLink)         | 22 AWG     | 3.3 V UART                 | §10 (copper-tape wrap) |

### 2.2 Pixhawk POWER (DF13 6-pin) pinout

Standard ArduPilot/PX4 power port. C5b + C2 install across pins 1 and 6 (or on the harness pair within 1" of the connector).

| Pin | Signal                         | Notes                                  |
|-----|--------------------------------|----------------------------------------|
| 1   | VCC (+5 V)                     | C5b (+) and C2 land here               |
| 2   | VCC (+5 V) (same rail)         |                                        |
| 3   | V_BAT analog                   | **Floating** (no Power Module under FAR-1) |
| 4   | I_BAT analog                   | **Floating** (no Power Module under FAR-1) |
| 5   | GND                            |                                        |
| 6   | GND                            | C5b (−) and C2 land here               |

> Pixhawk telemetry V/I will read 0 — accepted under FAR-1 mission profile per WG-3 §2.4.

### 2.3 ESP32-S3 breakout — VIN / GND

C4 + C2 land directly across the **VIN** and adjacent **GND** header pins on the Meshnology breakout. Within 0.5" of the pins.

> **VIN is 12 V post-FAR-1**, not 5 V. This is the source of the C4 = 25 V+ requirement.

---

## 3 — Universal Rules (read once, apply everywhere)

1. **Parallel caps share the same solder points.** Every electrolytic in this procedure is paired with a 100 nF ceramic on the same junction. Both must be present — the electrolytic catches low-frequency, the ceramic catches HF.
2. **Electrolytic polarity.** Long lead / no stripe → (+). Stripe / shorter lead → (−). Reversed = popped cap, sometimes violently. Check every one before energizing.
3. **Ceramics have no polarity.**
4. **Voltage rating is a ceiling, not a target.** 50 V cap on a 5 V rail is fine. Busbar-side caps need 50 V+ minimum to survive ESC transients (rail is 22–26 V plus spikes).
5. **Clip-on ferrites = (+) wire only.** Single exception: **F4** on P20 takes both (+) and (−) together for common-mode filtering.
6. **F1 toroid = single pass.** One wire through the hole, no multi-turn at these currents.
7. **F5 axial beads = inline.** Cut the signal wire, solder bead in series, heat-shrink. **Not used up-front under FAR-1** — pH is UART, not I²C. Pool-test-gated only.
8. **Lead length is everything.** Every mm between a cap and the pin it protects is series inductance that kills HF filtering. Cut leads short.
9. **Copper tape shields grounded at ONE end only** (source). Ungrounded = antenna. Both ends = ground loop.
10. **Install order:** busbar caps → input ferrites → wire the branches → output ferrites → output caps → sensor filtering → copper tape last → multimeter test → reinsert fuses (MIDI then MRBF last).
11. **Per-section continuity check.** After every numbered section below, multimeter (+) → (−) at the install point. Must read **open (>1 MΩ)** before moving on. Every section ends with this gate.
12. **Secure everything.** Marine vehicle = vibration. Zip-tie or hot-glue every cap and ferrite so nothing swings.

---

## 4 — Step-by-Step Procedure

### §1 — Busbar Bypass (DO THIS FIRST)

Highest-priority filter. Catches ESC switching at the source bus.

- [ ] **1.1** Verify busbar dead: multimeter across (+)/(−) studs reads **<0.1 V**.
- [ ] **1.2** Prep **C1 (1000 µF / 35 V+ electrolytic):** crimp ring terminals to leads, leads <1".
- [ ] **1.3** Mount C1 across (+) and (−) busbar studs. **Polarity:** long lead / no stripe → (+) stud.
- [ ] **1.4** Prep **C2 (100 nF / 50 V+ ceramic):** leads trimmed to <0.5".
- [ ] **1.5** Mount C2 in PARALLEL with C1 — same two studs, same solder joints. No polarity.
- [ ] **1.6** Torque busbar studs to spec (do not over-torque). Zip-tie both caps so they cannot swing under vibration.
- [ ] **1.7** **Continuity gate:** (+) → (−) busbar must read **open (>1 MΩ)**. If it shorts, stop and inspect — almost always a reversed C1 or a stray strand.

> **Common mistakes:** C1 reversed (long lead landed on (−)). C2 missing — busbar then filters low-freq only. Lead-length too long — under-torqued ring terminal forced you to leave 1.5" of bare lead, which becomes an inductor.

### §2 — ESC / Motor Branch (F1 + C3 + C2)

Single biggest noise source in the system. Do not skip any of it.

- [ ] **2.1** Identify the **8 AWG RED (+)** lead **P5** between MIDI 60 A fuse and ESC input.
- [ ] **2.2** Disconnect P5 at ESC end. Pass the 8 AWG wire through **F1 (Hondark 38×19×13 mm MnZn toroid)** — **single pass, one time through.** Do NOT wrap.
- [ ] **2.3** Position F1 within **2"** of ESC power input. Zip-tie F1 to the 8 AWG or adjacent structure so it cannot slide.
- [ ] **2.4** Reconnect 8 AWG to ESC (+) terminal.
- [ ] **2.5** Prep **C3 (470 µF / 35 V+ LOW-ESR electrolytic** — the **only** cap where low-ESR matters). Leads <0.5".
- [ ] **2.6** Solder C3 directly across ESC (+) and (−) power input terminals. **Polarity matters.**
- [ ] **2.7** Solder **C2 (100 nF / 50 V+ ceramic)** in PARALLEL with C3 — same terminals.
- [ ] **2.8** Heat-shrink the joints. Zip-tie.
- [ ] **2.9** **Continuity gate:** ESC (+) → (−) must read **open**, not shorted.

> **Common mistakes:** Multi-turn through F1 (don't — single pass at this current). Substituting standard-ESR for C3 (the high-current transients need low-ESR specifically here). F1 too far from ESC (must be <2"; the wire between the toroid and the ESC input is unfiltered).

### §3 — 12V Buck INPUT (F2 on P9)

12V buck now feeds three loads: Jetson DC barrel, cooling fan, and ESP32-S3 VIN. Input-side filter happens here; output-side filtering is split between the loads (§5).

- [ ] **3.1** Identify **P9** — 12 AWG RED (+) wire from ATO 3 A SB fuse to 12V buck input.
- [ ] **3.2** Snap **F2 (Raogoodcx 13 mm clip-on)** around the **(+) wire only** (not both wires). Within **2"** of the buck input.
- [ ] **3.3** Close clip-on, secure with tape or zip tie.
- [ ] **3.4** **Continuity gate:** P9 (+) at buck input → P10 (−) reads **open**.

> **Common mistakes:** Snapping the clip-on around both P9 and P10 — that's common-mode filtering, which is wrong here. The ESC-side noise is differential and you need it suppressed differentially. Common-mode is reserved for the ESP32 output (F4, §5).

### §4 — 5V Buck INPUT (F2 on P11)

Mirror of §3 for the Pixhawk-feeding rail.

- [ ] **4.1** Identify **P11** — 12 AWG RED (+) wire from ATO 2 A SB fuse to 5V buck input.
- [ ] **4.2** Snap **F2 (second 13 mm clip-on)** around the **(+) wire only**. Within **2"** of the 5V buck input.
- [ ] **4.3** Close, secure.
- [ ] **4.4** **Continuity gate:** P11 (+) → P12 (−) at buck input reads **open**.

### §5 — 12V Buck OUTPUT (F4 on P20, C4 + C2 at ESP32, C5 + C2 at Jetson)

The 12V buck output fans three ways. The ESP32 leg gets its own common-mode ferrite plus output caps; the Jetson barrel gets output caps; the fan needs nothing.

#### 5a. Common-mode ferrite F4 on the ESP32 leg

- [ ] **5.1** Identify **P20** — 22 AWG pair from 12V buck output to ESP32-S3 VIN.
- [ ] **5.2** Snap **F4 (Raogoodcx 6–13 mm clip-on)** around **BOTH (+) and (−)** wires of P20 **together**. Common-mode filter. Within **2"** of the ESP32 board.
- [ ] **5.3** Close, secure. (Sole exception to the "+ only" rule — see Section 3 / Universal Rules, rule 5.)

#### 5b. Output caps at ESP32 VIN

- [ ] **5.4** Prep **C4 (10 µF / 25 V+ electrolytic)** + **C2 (100 nF ceramic)**. Leads as short as possible.
  > **C4 voltage rating gate:** ESP32 VIN is 12 V post-FAR-1 (not 5 V as the BOM says). A 10 V-rated cap will fail. Verify the cap on your bench reads **25 V** or higher before soldering.
- [ ] **5.5** Solder C4 + C2 in PARALLEL across the ESP32 **VIN** and **GND** header pins. C4 polarity matters. Within **0.5"** of the header pins.
- [ ] **5.6** **Continuity gate:** ESP32 VIN → GND reads **open**.

#### 5c. Output caps at Jetson DC barrel

- [ ] **5.7** Prep **C5 (100 µF / 25–50 V electrolytic)** + **C2 (100 nF ceramic)**.
- [ ] **5.8** Solder C5 + C2 in PARALLEL across the Jetson 12 V DC barrel input pigtail (before the barrel plug). C5 polarity matters. Within **1"** of the barrel.
- [ ] **5.9** **Continuity gate:** Jetson 12 V input → GND reads **open**.

> Fan runs off the same 12V output via its JST connector — no extra filtering by design.

> **Common mistakes:** C4 = 10 V cap from BOM stock — installs and dies on first power-on (see Deviations table). F4 around only one wire — that's a differential-mode filter, but the ESP32 leg's worst noise is common-mode pickup from radiated ESC EMF. Solder joints >0.5" from ESP32 header pins — leads become inductors that kill HF filtering at the radio.

### §6 — 5V Buck → Pixhawk POWER Branch (C5b + C2 at DF13)

**FAR-1 NEW.** The dedicated 5V Power Module is gone. The generic 5V buck has no internal filtering — this branch needs its own bulk + HF bypass at the DF13 connector or you will see Pixhawk brownouts on ESC arm.

- [ ] **6.1** Locate the Pixhawk **POWER** port (DF13 6-pin).
- [ ] **6.2** Prep **C5b (47 µF / 10 V+ electrolytic)** + **C2 (100 nF ceramic)**. Leads as short as possible.
- [ ] **6.3** Solder C5b + C2 in PARALLEL across **+5 V (pin 1)** and **GND (pin 6)** of the DF13 6-pin connector — or on the P21 harness pair within **1"** of the connector. C5b polarity matters.
- [ ] **6.4** **Continuity gate:** +5 V → GND at the connector reads **open**, not shorted.

> **Brownout watch (post-install):** If Pixhawk resets during ESC arm or motor calibration, the generic buck is sagging under inrush. Mitigations in priority order: (1) Add a Schottky series diode + larger bulk cap at the POWER input; (2) revert this branch to a dedicated Pixhawk Power Module (and remove C5b + C2 — the Power Module reintroduces internal filtering).

> **Common mistakes:** Skipping C5b ("the buck regulates fine on the bench"). Yes — until ESC inrush slams the rail. The bulk cap is what catches the sag.

### §7 — Starlink Branch (F3 + C7 + C2)

- [ ] **7.1** Identify **P7** — 12 AWG RED (+) from ATO 7.5 A SB fuse to Starlink DC input.
- [ ] **7.2** Snap **F3 (13 mm clip-on)** around (+) wire only. Within **3"** of the **fuse block** (catch the noise near the source — the Starlink run is long).
- [ ] **7.3** Prep **C7 (100 µF / 35–50 V electrolytic)** + **C2 (100 nF ceramic)**.
- [ ] **7.4** Solder C7 + C2 in PARALLEL across the Starlink DC connector pigtail. C7 polarity matters. Within **1"** of the connector. Heat-shrink the joints.
- [ ] **7.5** **Continuity gate:** Starlink (+) → (−) at the plug reads **open**.

> **Common mistakes:** F3 placed at the Starlink end instead of the fuse end — Starlink has its own internal conditioning, so the goal is to prevent ESC noise from coupling onto the long P7 run, which means catching it at the source.

### §8 — BEC → Servo Branch (C6 + C2, no ferrite by design)

- [ ] **8.1** Prep **C6 (100 µF / 16–50 V electrolytic)** + **C2 (100 nF ceramic)**.
- [ ] **8.2** Solder C6 + C2 in PARALLEL across the (+) and (−) wires of the **P22** servo cable. **At the servo end**, not the BEC end (the servo is the inductive noise source; the cap absorbs there). C6 polarity matters. Within **1"** of the servo 3-pin connector.
- [ ] **8.3** Heat-shrink the junction.
- [ ] **8.4** **Continuity gate:** servo (+) → (−) reads **open**.

> No input ferrite on this branch by design — see WG-3 §4.2.

### §9 — Sensor Signal Filtering (TDS critical, pH gated, 1-Wire optional)

> **FAR-1 reality check:** pH path is **UART @ 9600 baud** per `firmware/main/sensor_bridge.c` — not I²C. F5 BOJACK beads are **not installed up-front**. Do not cut and splice beads inline. If pool-test reveals UART framing errors with motor running, retrofit a single 13 mm clip-on on the CAT6 at the ESP32 end. Document and re-verify.

#### 9a. CRITICAL — TDS analog (S10)

- [ ] **9.1** Solder **C2 (100 nF ceramic)** between the ESP32 ADC pin reading TDS (S10) and ESP32 GND. **Within 0.25" of the ESP32 pin** — this is the strictest distance gate in the procedure. ADC accuracy depends on it.
- [ ] **9.2** Solder direct to header pin or breakout pad. Shortest possible leads.
- [ ] **9.3** **Continuity gate:** TDS pin → GND reads **open** (cap acts as open at DC).

#### 9b. SKIP up-front — pH UART (S8)

- [ ] **9.4** **DO NOT install F5 beads on pH lines.** Do not cut/splice the CAT6 pH pair. This step is intentionally a no-op at install time. Reassess after pool test (§troubleshooting).

#### 9c. OPTIONAL — 1-Wire DS18B20 (S9)

- [ ] **9.5** *(Optional, defer unless visible noise.)* Solder C2 (100 nF ceramic) between the ESP32 1-Wire data pin (S9) and GND, **<0.5" from the pin**.

#### 9d. DO NOT INSTALL — S7 IMU, S11 GPS

- [ ] **9.6** S7 (IMU) and S11 (GPS) are removed in WG-2 (replaced by Pixhawk built-in IMU and M8N GPS). Any beads or caps the BOM specified for these lines are **not needed** — skip entirely.

> **Common mistakes:** TDS cap landed on a long jumper to GND — that 1" of wire kills the filter. C2 must reach the ADC pin and the nearest GND pin in well under a quarter-inch.

### §10 — Copper Tape Shielding (DO LAST — after all filters installed and bench-verified)

Copper tape goes innermost (the conductive layer) → automotive self-adhesion tape (insulation, prevents shorts to neighbors) → split loom (mechanical protection). Drain wire grounded at **ONE end only** (source). Leave **0.5"** bare at connectors so the tape doesn't short to pins.

#### 10a. Cable-body wraps

- [ ] **10.1** **P20** (12V buck → ESP32, 22 AWG pair):
  - Wrap the cable body in copper tape. Slight overlap, no gaps.
  - Solder a **2"** drain pigtail (22–26 AWG) to the copper tape **at the 12V buck (source) end**.
  - Land the drain pigtail on the **12V buck GND** terminal.
  - Leave the ESP32 end of the tape **floating** (no drain).
  - Cover the entire copper tape run with automotive self-adhesion tape (SH2) so it can't short to neighbors.
- [ ] **10.2** **S1** (ESP32 UART → Pixhawk JST-SH 4-pin):
  - Same procedure as P20 but smaller cable.
  - Drain at the **ESP32 (source) end** → **ESP32 GND** at the breakout.
  - Pixhawk end floating.
- [ ] **10.3** **CAT6 sensor bundle** (S8/S9/S10): foil shield is built in. Verify the CAT6 foil drain is landed at **ESP32 GND only** (bow end floating). Should already be correct per WG-3 §3.2 — verify, do not re-route.

#### 10b. Component-body wraps (NEW under WG-2 — all to (−) busbar, ONE end only)

For each component below, wrap the full body of the device in copper tape, then automotive self-adhesion tape over it. Solder a **1–2"** drain pigtail (22–26 AWG) from the copper tape surface to the **(−) busbar**. **One drain per body. Never daisy-chain drains.**

- [ ] **10.4** **ESC body** — replaces the original heat shrink. Avoid covering heatsink fins (don't thermally trap the ESC). Drain → (−) busbar.
- [ ] **10.5** **BEC body** (Castle). Drain → (−) busbar.
- [ ] **10.6** **12V buck converter body.** Drain → (−) busbar.
- [ ] **10.7** **5V buck converter body.** Drain → (−) busbar.

#### 10c. After every copper-tape install

- [ ] **10.8** Cover all copper tape with automotive self-adhesion tape (SH2). Bare copper tape near other wiring will short something at the worst possible time.
- [ ] **10.9** **Continuity check per shield:** drain wire → its destination GND = **closed** (through ground path). Drain wire → any (+) rail = **open**. If a drain reads continuity to (+), the tape is touching a (+) terminal somewhere — find and insulate it.

#### 10d. Do NOT wrap

- CAT6 bow sensor bundle (S8/S9/S10) — foil shield handles it.
- P5/P6 ESC-motor 8 AWG — noise source, not victim. F1 + C3 + C2 handle it.
- P17 3-phase ESC → motor wires — noise source. Split loom only.
- P1–P4 4 AWG trunk — short, fat, low impedance; not worth shielding.
- S7, S11 — sensors removed in WG-2.
- S10 TDS individually — already inside the CAT6 foil.

> **Common mistakes:** Drain at both ends → ground loop, makes things worse. No insulation over copper tape → drain shorts to a neighbor terminal. Daisy-chained drains → multiple component-body shields share one inductive return path, defeating the point.

### §11 — Aluminum Plate Shielding (referenced from WG-3 §5; status: design only, parts on hand)

The grounded 12×24" aluminum mounting plate is a conductive shield between ESC (mounted underneath) and topside electronics (Jetson, Pixhawk, ESP32, converters). **Status per WG-3 §5: DESIGN ONLY, parts on hand, not yet implemented.** Bundled here because it's directly part of the EMI work; if you're skipping this section in the same install pass, mark §11 deferred and proceed to §12.

#### 11a. Plate prep (before mounting topside components)

- [ ] **11.1** Apply **Kapton tape** to the entire **top surface** of the aluminum plate. Double-layer wherever a ring terminal or bolt head will sit.
- [ ] **11.2** Install **dielectric thermal pads** under each converter footprint (12V buck, 5V buck, BEC).
- [ ] **11.3** Prep a **12 AWG BLK plate-ground jumper**: ring terminal → plate bolt at one end, the other end prepped for the (−) busbar.
- [ ] **11.4** Land the plate ground jumper on the **(−) busbar**. **Single point only — no second plate-to-ground anywhere on the boat.** A second tie = ground loop, kills the filtering scheme.

#### 11b. ESC under-plate mounting

- [ ] **11.5** Apply thermal pad to ESC underside. Mount ESC to the plate's **bottom surface** at the stern-ward end.
- [ ] **11.6** Drill/grommet a hole for the 8 AWG (P5/P6) power feed. Route through the grommet — wires must not contact bare plate edges.
- [ ] **11.7** Drill a separate small grommet hole for **S3 PWM** (Pixhawk → ESC). Route around plate edge or through this dedicated hole — keep separate from the 8 AWG power feed.
- [ ] **11.8** Conformal-coat the ESC PCB **OR** wrap the ESC body in closed-cell foam splash guard. ESC is now the lowest component in the hull and **will** see splash. Waterproofing is mandatory, not optional.

> **Critical rules (re-stated for emphasis):**
> - **Single ground point only** — no second plate-to-ground.
> - Kapton goes **under** every topside component. The plate is now live ground; a scraped trace or bare ring terminal edge = dead short.
> - ESC waterproofing is mandatory.

### §12 — Final Routing & Separation

- [ ] **12.1** Verify signal wires (22–26 AWG, CAT6) are physically routed **at least 12"** from 8 AWG motor power. Use opposite hull walls (signals starboard, power port — per WG-3 §6).
- [ ] **12.2** Confirm S3 PWM goes through its own grommet hole, not the 8 AWG hole.
- [ ] **12.3** Verify no copper tape edges contact unintended surfaces. Add SH2 patches anywhere a tape edge is close to a (+) terminal.
- [ ] **12.4** Tug-test every soldered joint. Re-zip-tie any cap that can swing.

---

## 5 — Post-Install Verification (V1–V6)

Do all six in order. Stop on the first failure; do not skip ahead.

- [ ] **V1. Visual inspection.** No loose solder, no pinched wires, all caps secured, no copper tape touching unintended surfaces. Polarity of every electrolytic visually re-checked.
- [ ] **V2. Full busbar continuity.** (+) → (−) on the busbar = **open (>1 MΩ)**. If shorted anywhere, stop and find it before re-energizing.
- [ ] **V3. Smoke test.** Reconnect battery at kill switch (insert MIDI 60 A, then MRBF **last**). Look for smoke. (Yes, really.)
- [ ] **V4. Per-rail voltage.** Multimeter at each branch output:
  - Busbar = **22–26 V** (depending on demo vs production battery state).
  - 5V buck output to Pixhawk POWER (P21) = **5.0 ± 0.1 V**.
  - 12V buck output to Jetson + ESP32 + fan = **12.0 ± 0.2 V**.
  - BEC output (P22) = per BEC spec (typically 5.5 V or 6 V).

  > *Removed under FAR-1:* the old "Pixhawk 5V rail from Power Module" check no longer applies. Pixhawk POWER is now fed by the 5V buck (P21) and is checked above.

- [ ] **V5. Motor spin-up.** Power on motor briefly with **prop removed**, low throttle. No smoke, no abnormal buzz, no rail sag >0.5 V on any branch.
- [ ] **V6. Compass-drift gate.** Open QGC, watch heading. With motor OFF: heading is stable. With motor running at low throttle: heading shifts **<2°** from static value. **>5° shift = EMI is still a problem** — re-inspect §2 (ESC branch) and §11 plate ground.

---

## 6 — Update Docs After Install (deferred — track but not in scope today)

- Update `AQUABOTS_EMI_FILTERING_BOM.pdf` status column (ORDER → INSTALLED). Deferred — BOM Rev ISR-5 regen is a separate task.
- Update `AQUABOTS_POWER_SYSTEM_CHANGELOG.md` with install date and append Rev ISR-5 block.
- Bump `AQUABOTS_WIRING_GUIDE.md` WG-3 → WG-4 with summary: "EMI filtering installed. Production DSServo + new BEC wired. Compass + accel recalibrated post-install."
- Record SERVO1 calibration values (MIN/MAX/TRIM/REVERSED) in the wiring guide or a new `PIXHAWK_SERVO_CONFIG.md`.

---

## 7 — Known Deviations from BOM Rev ISR-4b

| BOM Rev ISR-4b says                                  | This procedure does                                                              | Reason |
|------------------------------------------------------|----------------------------------------------------------------------------------|--------|
| 4 ferrite beads on I²C (2 pH SDA + 2 SCL) + 2 optional UART | **0 F5 beads up-front.** Pool-test-gated CAT6 clip-on only.            | Per `firmware/main/sensor_bridge.c`, pH is UART @ 9600 baud. I²C beads not needed. |
| 2 ferrite beads on IMU SDA/SCL                       | **0** — sensor removed.                                                          | S7 IMU removed in WG-2. Pixhawk built-in IMU. |
| Copper tape on P21, S10 individual, optional S1/S2   | **P20** (not P21) + S1 + ESC body + BEC body + 12V buck body + 5V buck body.     | FAR-1 moved ESP32 to 12V buck rail (P21 → P20). WG-2 added component-body wraps for radiated emission. CAT6 foil already shields S10, so individual wrap removed. |
| 5V Power Module on Pixhawk POWER (internal filtering) | **Generic 5V buck + C5b 47 µF/10 V+ + C2 100 nF.**                              | FAR-1 consolidation — Power Module removed, generic buck has no internal filtering. |
| C4 = 10 µF / 10 V+ on ESP32 VIN                      | **C4 = 10 µF / 25 V+** electrolytic.                                             | ESP32 VIN is 12 V post-FAR-1, not 5 V. 10 V cap would fail. |
| F4 location: "5V Buck output to ESP32"               | **F4 on P20 (12V Buck output to ESP32 pair).**                                   | ESP32 moved from 5V buck rail to 12V buck rail under FAR-1. |
| C2 ceramic qty "10+"                                 | ~9 used (~10–12 with optional 1-Wire and spares). BOM qty is sufficient.         | Qty unchanged in spirit; reflect actual install.   |

These deviations feed into BOM Rev ISR-5 regeneration (separate task, not in scope for this install).

---

## 8 — Troubleshooting & Fallback

If V1–V6 fail, follow this triage tree before reaching for a different design.

| Symptom                                            | First place to check                                       | Mitigation                                                                                          |
|----------------------------------------------------|------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| **V2 fails — busbar shorted**                      | C1 polarity reversed, or stray wire strand across studs.   | Disconnect C1, re-test. If now open, C1 was reversed; replace.                                      |
| **V3 fails — smoke / smell on power-up**           | Reversed electrolytic somewhere; or copper tape shorting.  | Kill power. Identify which converter is hot. Inspect every electrolytic in that branch. Re-check copper-tape insulation per §10c. |
| **V4 fails — Pixhawk 5 V rail low (<4.9 V)**       | C5b missing or sagging buck under load.                    | Re-verify §6. If C5b is in place: add Schottky series + larger bulk cap, or revert to dedicated Pixhawk Power Module. |
| **V4 fails — ESP32 12 V rail low**                 | F2 wired around both wires (= common-mode, wrong here).    | Re-do §3 with F2 around (+) only.                                                                   |
| **V5 fails — Pixhawk reset on ESC arm/calibration** | Brownout: 5V buck sagging during inrush.                  | Per §6 brownout watch — Schottky + bulk, or revert to Power Module.                                 |
| **V5 fails — abnormal motor buzz**                 | F1 not single-pass (multi-turn = saturated core).          | Re-do F1 as single pass.                                                                            |
| **V6 fails — compass drift >5° with motor on**     | ESC body not shielded; F1 too far from ESC; copper-tape drain bonded at wrong end. | Re-verify §2.3 (F1 within 2"), §10.4 (ESC body wrapped, drain to (−) busbar at one end), §11.4 (plate ground = single point). |
| **Pool test — pH UART framing errors with motor on** | Conducted noise on CAT6.                                 | Add **one** 13 mm clip-on ferrite on the CAT6 bundle at the ESP32 end. Do **not** cut/splice F5 beads inline. Document and re-run V6. |
| **Pool test — TDS reading noisy with motor on**    | C2 at ADC pin too far from pin, or missing.                | Re-solder C2 to <0.25" from the ADC pin. If still noisy after that, add a clip-on ferrite on the CAT6 at the ESP32 end (same retrofit as pH). |
| **Compass drift fixed by detaching plate ground**  | Ground loop — second plate-to-ground tie somewhere.        | Find the second tie. Per §11.4 only **one** plate-to-(−)-busbar connection.                         |

### Optional pool-test-gated additions (only if symptoms appear)

- CAT6 clip-on ferrite at ESP32 end — for pH UART or TDS noise (one ferrite covers both since they share the bundle).
- Schottky + larger bulk cap at Pixhawk POWER input — for buck brownout under ESC inrush.
- Revert 5V buck → dedicated Pixhawk Power Module — last resort, restores telemetry V/I and internal filtering.

---

## 9 — Do-Not-Do List (re-stated)

- Do **NOT** energize anything until **all** §-end continuity gates pass.
- Do **NOT** ground both ends of any shield. Source end only.
- Do **NOT** multi-turn the F1 toroid. Single pass only.
- Do **NOT** swap F4 from common-mode (both wires) to single-wire. Topology is intentional.
- Do **NOT** skip the 100 nF ceramic in any parallel pair. Electrolytic alone covers low-frequency only.
- Do **NOT** cut and splice F5 beads inline on pH SDA/SCL — pH is UART, not I²C.
- Do **NOT** use a 10 V-rated cap on the ESP32 VIN rail — it's 12 V post-FAR-1.
- Do **NOT** skip C5b at the Pixhawk POWER connector — the old Power Module's internal filtering is gone.
- Do **NOT** add a second plate-to-ground tie — single point only or the whole filtering scheme falls apart.

---

*Companion documents (still authoritative for their domains):*

- `AQUABOTS_WIRING_GUIDE.md` Rev WG-3 — wire IDs, connector pinouts, rail layout, routing.
- `AQUABOTS_EMI_FILTERING_BOM.pdf` Rev ISR-4b — parts catalog (with deviations per §7 above).
- `AQUABOTS_POWER_SYSTEM_CHANGELOG.md` — full revision history.

*Predecessor docs (stubbed, do not reference):*

- `AQUABOTS_EMI_INSTALL_GUIDE.md` Rev WG-3 / FAR-1 — merged into this procedure.
- `field-procedures/EMI_FILTERING_INSTALL_CHECKLIST.md` FAR-1 patched — merged into this procedure.
