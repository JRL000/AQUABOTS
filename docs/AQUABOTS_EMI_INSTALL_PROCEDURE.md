---
title: "AQUABOTS EMI Install Procedure"
subtitle: "Team 26061 · ENGR 498B Spring 2026 · Rev WG-2"
author: "Owner: John"
date: "2026-04-26"
geometry: "margin=0.7in"
fontsize: 10pt
---

# AQUABOTS EMI Install Procedure — Rev WG-2

**Team 26061 | Rev WG-2 | 2026-04-26**

Single-document EMI install procedure for the AQUABOTS hull, aligned to the **as-built WG-2 power topology**. FAR-1 was a paper-only architecture change (consolidate ESP32 onto the 12V rail; replace the dedicated Pixhawk Power Module with a generic 5V buck) that was never installed — this procedure is for the actual hardware on the bench: dedicated 5V Power Module on Pixhawk, ESP32 on its own 5V buck.

Supersedes the prior `AQUABOTS_EMI_INSTALL_GUIDE.md` and `EMI_FILTERING_INSTALL_CHECKLIST.md`. Pinouts and wire IDs match the WG-2 topology (five ATO branches). Where this procedure deviates from `AQUABOTS_EMI_FILTERING_BOM.pdf` Rev ISR-4b, the deviations table at the end gives the reasons.

**Goal:** Physically install all EMI filtering (caps, ferrites, copper tape, plate ground) on the WG-2 topology. Required before extended motor testing or any auto-mode water test — motor EMF will destroy compass/GPS data otherwise.

**Estimated time:** 2–3 hours (soldering + per-section continuity checks + shielding). Add ~45 min for the aluminum plate shielding sub-procedure if doing it in the same session.

**This document is the single source of truth for the install. Do not flip back to the predecessor docs — they have been stubbed.**

---

## 0 — Pre-Install Supply Gathering (READ FIRST)

Pull every part on this list onto the bench before unscrewing anything. Sections 0.1–0.4 are the complete shopping/staging list.

### 0.1 Components — caps, ferrites, beads

Quantities reflect WG-2 reality (no C5b; C4 = 100 µF / 16 V; F4 on **P20** common-mode; F5 beads zero up-front, optional pool-test-gated; Pixhawk fed by a dedicated 5V Power Module — that branch carries **no** EMI components beyond the universal busbar pair). Cross-checked against BOM Rev ISR-4b — see "Known Deviations from BOM" at the end.

| ID  | Value / rating                       | Qty | Where it goes                                       |
|-----|--------------------------------------|-----|-----------------------------------------------------|
| C1  | 1000 µF / 35 V+ electrolytic         | 1   | Busbar (+)/(−) studs (§1)                           |
| C2  | 100 nF / 50 V+ ceramic disc          | ~8  | Busbar; ESC; ESP32 5V input; Jetson barrel; Starlink; servo; TDS ADC; (+1 optional 1-Wire) |
| C3  | 470 µF / 35 V+ **LOW-ESR** electrolytic | 1   | ESC (+)/(−) input terminals (§2)                  |
| C4  | **100 µF / 16 V+** electrolytic      | 1   | ESP32 VIN / GND, <0.5" from header (§5) — 5 V rail, bulk + ride-through. **NOT 10 µF / 10 V from BOM.** |
| C5  | 100 µF / 25–50 V electrolytic        | 1   | Jetson DC barrel (§3)                               |
| C6  | 100 µF / 16–50 V electrolytic        | 1   | Servo 3-pin connector (§7)                          |
| C7  | 100 µF / 35–50 V electrolytic        | 1   | Starlink DC plug (§6)                               |
| F1  | Hondark MnZn ferrite toroid 38×19×13 mm | 1 | P5 (8 AWG +) at ESC end, single pass (§2)         |
| F2  | Raogoodcx 13 mm clip-on ferrite      | 2   | P11 (12V buck input) + P13 (5V buck input) (§3, §5) |
| F3  | Raogoodcx 13 mm clip-on ferrite      | 1   | P7 (Starlink +) at fuse end (§6)                    |
| F4  | Raogoodcx 6–13 mm clip-on ferrite    | 1   | **P20** (5V buck → ESP32 pair, BOTH wires, common-mode) (§5) |
| F5  | BOJACK ~70 Ω @ 100 MHz axial bead    | **0** | **Optional / pool-test-gated.** pH firmware is UART (per `firmware/main/sensor_bridge.c`), not I²C — do NOT cut/splice F5 beads up-front. If pool-test reveals UART framing errors with motor on, retrofit a single CAT6 clip-on at the ESP32 end. (§8) |

> **No C5b under WG-2.** The Pixhawk POWER port is fed by a dedicated 5V Power Module (P21), which has its own internal filtering. Do not add a C5b cap on this branch — there's no place for it and no need for it.

### 0.2 Wire, cable, shield, hardware

| Item                                        | Spec / size                          | Approx qty           |
|---------------------------------------------|--------------------------------------|----------------------|
| Copper foil tape (conductive adhesive) — SH1 | 1" wide                              | ~1 roll (10+ ft used: P20 cable + S1 cable + 5 component bodies) |
| Automotive self-adhesion (electrical) tape — SH2 | Standard                          | 1 roll               |
| Split loom — SH3                            | 1/4" and 3/8" ID                     | as needed            |
| Heat shrink                                 | Assorted (1/16"–1/2")                | full assortment      |
| Drain wire pigtails                         | 22–26 AWG, ~2" each                  | 7 (one per shield: 2 cables + 5 component bodies) |
| Ring terminals                              | SC (M5/M6) for busbar studs          | 2 (for C1 leads)     |
| Zip ties                                    | Small                                | ~25                  |
| Kapton tape (plate prep — §10 only)         | 2" wide                              | 1 roll (on hand)     |
| Thermal pads (plate prep — §10 only)        | Dielectric silicone, ~50×50 mm sized to converter footprint (12V buck, 5V buck, BEC, Power Module, ESC underside) | 5 pads (on hand) |
| 12 AWG plate ground jumper (§10 only)       | BLK, ~6"                             | 1                    |

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
- Kapton tape — see §10 plate prep
- Dielectric grease — for the DF13 6-pin Pixhawk POWER connector pin housing only (not on contacts)
- Thermal pads — see §10 plate prep (sized per converter footprint)

---

## 1 — Prerequisites & Safety

- [ ] Main battery **DISCONNECTED** at kill switch.
- [ ] Multimeter across busbar reads **<0.1 V**. If not, find what is back-feeding before going further.
- [ ] All converters off. No LEDs lit anywhere on the plate.
- [ ] MIDI 60 A and MRBF fuse elements **removed** (re-insert during V3 smoke test).
- [ ] ESD strap on; bench has ESD-safe surface.
- [ ] Ventilation for soldering. Leaded solder fumes are not your friend.
- [ ] This procedure document open. Predecessor `AQUABOTS_EMI_INSTALL_GUIDE.md` and `EMI_FILTERING_INSTALL_CHECKLIST.md` have been stubbed and should not be referenced.
- [ ] `AQUABOTS_WIRING_GUIDE.md` Rev WG-2 nearby for layout reference (this procedure embeds wire IDs but the wiring guide governs routing).
- [ ] BOM PDF `AQUABOTS_EMI_FILTERING_BOM.pdf` Rev ISR-4b nearby — but treat as stale where it conflicts with this procedure. See "Known Deviations from BOM" at the end.

---

## 2 — Reference: Wire IDs and Pinouts (embedded so you don't flip)

WG-2 power topology — **five ATO branches**, dedicated 5V Power Module on Pixhawk, ESP32 fed by its own 5V buck.

### 2.1 Wire IDs touched in this procedure

| Wire ID    | Path                                                  | Gauge      | Rail / signal            | Used in section |
|------------|-------------------------------------------------------|------------|--------------------------|-----------------|
| P5 (a/b/c) | (+) Busbar → MIDI 60 A → F1 → ESC (+) input           | 8 AWG RED  | 22–26 V (busbar)         | §2 (ESC branch) |
| P6         | (−) Busbar → ESC (−) input                            | 8 AWG BLK  | GND                      | §2              |
| P7 (a/b/c) | (+) Busbar → ATO 7.5 A → F3 → Starlink DC (+)         | 12 AWG RED | 22–26 V                  | §6 (Starlink)   |
| P8         | (−) Busbar → Starlink DC (−)                          | 12 AWG BLK | GND                      | §6              |
| **P9 (a/b)** | (+) Busbar → ATO 2 A → 5V Power Module (+)          | 12 AWG RED | 22–26 V → Power Module   | §4 (Pixhawk via Power Module) |
| P10        | (−) Busbar → 5V Power Module (−)                      | 12 AWG BLK | GND                      | §4              |
| **P11 (a/b/c)** | (+) Busbar → ATO 3 A → F2 → 12V buck input (+)   | 12 AWG RED | 22–26 V → 12V buck       | §3 (12V buck branch) |
| P12        | (−) Busbar → 12V buck input (−)                       | 12 AWG BLK | GND                      | §3              |
| **P13 (a/b/c)** | (+) Busbar → ATO 1 A → F2 → 5V buck input (+)    | 12 AWG RED | 22–26 V → 5V buck        | §5 (5V buck → ESP32) |
| P14        | (−) Busbar → 5V buck input (−)                        | 12 AWG BLK | GND                      | §5              |
| P15 (a/b)  | (+) Busbar → ATO 2 A → BEC input (+)                  | 12 AWG RED | 22–26 V → BEC            | §7 (BEC/servo)  |
| P16        | (−) Busbar → BEC input (−)                            | 12 AWG BLK | GND                      | §7              |
| P17        | ESC 3-phase → Motor 5080                              | 8 AWG ×3   | 3-phase motor            | (do not wrap; noise source) |
| P18        | 12V buck → Jetson DC barrel                           | 22 AWG pr  | 12 V                     | §3              |
| P19        | 12V buck → Cooling fan                                | 22 AWG pr  | 12 V                     | (no extra filter) |
| **P20 (a/b)** | 5V buck → F4 → ESP32-S3 breakout VIN               | 22 AWG pr  | **5 V** (WG-2)           | §5 (F4 + C4 + C2; copper-tape wrap §9) |
| **P21**    | **5V Power Module** → Pixhawk 4X **POWER** (DF13 6-pin) | 22 AWG pr | 5.0 V                    | §4 (no EMI components — Power Module has internal filtering) |
| P22        | BEC (Castle) → Rudder Servo                           | 22 AWG pr  | 5.5 / 6 V (BEC spec)     | §7              |
| S1         | ESP32 UART1 <-> Pixhawk (MAVLink)                       | 22 AWG     | 3.3 V UART               | §9 (copper-tape wrap) |
| S2         | Pixhawk TELEM2 <-> Jetson                               | 22 AWG     | 3.3 V UART               | (no copper-tape wrap unless pool-test gated) |

> **P20 vs P21 — do not conflate.** They are separate branches with the same 22 AWG gauge but different rails and different filter loadouts:
> - **P20** = 5V buck (P13/P14 input) → F4 (common-mode) → ESP32 VIN. Caps C4 + C2 land at the ESP32 header.
> - **P21** = 5V Power Module (P9/P10 input) → Pixhawk POWER DF13. **No** added EMI components on this branch.

### 2.2 Pixhawk POWER (DF13 6-pin) pinout

Standard ArduPilot/PX4 power port. **No C-bypass install on this branch** — the dedicated Power Module includes internal filtering; adding caps here is unnecessary and potentially destabilizing.

| Pin | Signal                         | Notes                                  |
|-----|--------------------------------|----------------------------------------|
| 1   | VCC (+5 V)                     | From Power Module                      |
| 2   | VCC (+5 V) (same rail)         |                                        |
| 3   | V_BAT analog (battery V sense) | Live — Power Module provides telemetry |
| 4   | I_BAT analog (battery I sense) | Live — Power Module provides telemetry |
| 5   | GND                            |                                        |
| 6   | GND                            |                                        |

### 2.3 ESP32-S3 breakout — VIN / GND

C4 + C2 land directly across the **VIN** and adjacent **GND** header pins on the Meshnology breakout. Within 0.5" of the pins.

> **VIN is 5 V under WG-2** (fed by the 5V buck via P20, with F4 in series as a common-mode filter on the pair). C4 = 100 µF / 16 V+ for ride-through and bulk on the 5V rail. The 10 µF / 10 V cap from BOM ISR-4b is undersized for ride-through here — see deviations table.

---

## 3 — Universal Rules (read once, apply everywhere)

1. **Parallel caps share the same solder points.** Every electrolytic in this procedure is paired with a 100 nF ceramic on the same junction. Both must be present — the electrolytic catches low-frequency, the ceramic catches HF.
2. **Electrolytic polarity.** Long lead / no stripe → (+). Stripe / shorter lead → (−). Reversed = popped cap, sometimes violently. Check every one before energizing.
3. **Ceramics have no polarity.**
4. **Voltage rating is a ceiling, not a target.** 50 V cap on a 5 V rail is fine. Busbar-side caps need 50 V+ minimum to survive ESC transients (rail is 22–26 V plus spikes).
5. **Clip-on ferrites = (+) wire only.** Single exception: **F4** on P20 takes both (+) and (−) together for common-mode filtering.
6. **F1 toroid = single pass.** One wire through the hole, no multi-turn at these currents.
7. **F5 axial beads = inline.** Cut the signal wire, solder bead in series, heat-shrink. **Not used up-front under WG-2** — pH firmware is UART, not I²C. Pool-test-gated only.
8. **Lead length is everything.** Every mm between a cap and the pin it protects is series inductance that kills HF filtering. Cut leads short.
9. **Copper tape shields grounded at ONE end only** (source). Ungrounded = antenna. Both ends = ground loop.
10. **Pixhawk Power Module branch (P9/P21) gets no added caps or ferrites.** The Power Module has internal filtering. Don't add C5b — that was a paper-only FAR-1 idea, not a WG-2 reality.
11. **Install order:** busbar caps → input ferrites → wire the branches → output ferrites → output caps → sensor filtering → copper tape last → multimeter test → reinsert fuses (MIDI then MRBF last).
12. **Per-section continuity check.** After every numbered section below, multimeter (+) → (−) at the install point. Must read **open (>1 MΩ)** before moving on. Every section ends with this gate.
13. **Secure everything.** Marine vehicle = vibration. Zip-tie or hot-glue every cap and ferrite so nothing swings.

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

### §3 — 12V Buck Branch (F2 input on P11, C5 + C2 at Jetson)

The 12V buck feeds **two loads only** under WG-2: Jetson DC barrel and the cooling fan. Output filtering happens at the Jetson barrel; the fan needs nothing.

#### 3a. Input ferrite F2 on P11

- [ ] **3.1** Identify **P11** — 12 AWG RED (+) wire from ATO 3 A SB fuse to 12V buck input.
- [ ] **3.2** Snap **F2 (Raogoodcx 13 mm clip-on)** around the **(+) wire only** (not both wires). Within **2"** of the buck input.
- [ ] **3.3** Close clip-on, secure with tape or zip tie.
- [ ] **3.4** **Continuity gate:** P11 (+) at buck input → P12 (−) reads **open**.

#### 3b. Output caps at Jetson DC barrel

- [ ] **3.5** Prep **C5 (100 µF / 25–50 V electrolytic)** + **C2 (100 nF ceramic)**.
- [ ] **3.6** Solder C5 + C2 in PARALLEL across the Jetson 12 V DC barrel input pigtail (before the barrel plug). C5 polarity matters. Within **1"** of the barrel.
- [ ] **3.7** **Continuity gate:** Jetson 12 V input → GND reads **open**.

> Fan runs off the same 12V output via its JST connector — no extra filtering by design.
> **WG-2 note:** ESP32 is **not** on this rail. Don't try to land C4 / F4 here — those go in §5.

> **Common mistakes:** Snapping F2 around both P11 and P12 (= common-mode, wrong here — ESC noise on this branch is differential). Routing the ESP32 power off this branch (that's the FAR-1 paper architecture; under WG-2 the ESP32 has its own 5V buck — see §5).

### §4 — 5V Power Module → Pixhawk POWER Branch (NO added EMI components)

The Pixhawk POWER port (DF13 6-pin) is fed by a **dedicated 5V Power Module** on its own ATO 2 A SB branch (P9/P10). The Power Module includes internal bulk + HF filtering, so this branch needs **no** EMI components beyond the universal C1/C2 already on the busbar (§1). This section is a verify-and-leave-alone gate.

- [ ] **4.1** Visually verify: P9 (12 AWG) lands on the 5V Power Module input (with no clip-on ferrite, no input cap added). The Power Module is a sealed brick with its own filtering — don't add anything.
- [ ] **4.2** Verify P21 (22 AWG pair, DF13 6-pin) goes from the Power Module output to the Pixhawk POWER port directly. **No C5b. No clip-on. No cap pair at the connector.**
- [ ] **4.3** **Continuity gate:** P21 +5 V → GND at the Pixhawk POWER connector reads **open** with the Power Module disconnected from P9 (you're reading through the Module's internal load, but should not see a dead short).

> **Why no caps here:** the Power Module's internal filtering plus the busbar bulk (C1) is enough for the Pixhawk POWER input. Adding a bulk cap at the DF13 risks oscillation against the Power Module's regulation loop. (If you've previously read a procedure that called for C5b 47 µF / 10 V at the Pixhawk POWER connector — that was the FAR-1 architecture which replaced the Power Module with a generic buck. We are NOT on that architecture.)

> **Brownout watch (post-install):** If Pixhawk resets during ESC arm or motor calibration despite the Power Module, suspect (a) the Power Module is faulty / undersized, or (b) the busbar is sagging during inrush — check C1 and the trunk torque.

### §5 — 5V Buck → ESP32 Branch (F2 input on P13, F4 common-mode on P20, C4 + C2 at ESP32)

The ESP32-S3 breakout is the second-most EMI-sensitive load (after the Pixhawk compass) thanks to its 2.4 GHz radio and analog ADC inputs. This branch gets **two ferrites** (input F2, output F4 common-mode) plus output caps at the ESP32 VIN header.

#### 5a. Input ferrite F2 on P13

- [ ] **5.1** Identify **P13** — 12 AWG RED (+) wire from ATO 1 A SB fuse to 5V buck input.
- [ ] **5.2** Snap **F2 (second 13 mm clip-on)** around the **(+) wire only**. Within **2"** of the 5V buck input.
- [ ] **5.3** Close, secure.
- [ ] **5.4** **Continuity gate:** P13 (+) → P14 (−) at buck input reads **open**.

#### 5b. Common-mode ferrite F4 on P20 (output side)

- [ ] **5.5** Identify **P20** — 22 AWG pair from 5V buck output to ESP32-S3 VIN.
- [ ] **5.6** Snap **F4 (Raogoodcx 6–13 mm clip-on)** around **BOTH (+) and (−)** wires of P20 **together**. Common-mode filter. Within **2"** of the ESP32 board.
- [ ] **5.7** Close, secure. (Sole exception to the "+ only" rule — see Section 3 / Universal Rules, rule 5.)

#### 5c. Output caps at ESP32 VIN

- [ ] **5.8** Prep **C4 (100 µF / 16 V+ electrolytic)** + **C2 (100 nF ceramic)**. Leads as short as possible.
  > **C4 voltage rating gate:** ESP32 VIN is 5 V (P20 from the 5V buck). 16 V+ rating gives 3× headroom. Do **not** install a 10 V cap here even though BOM ISR-4b lists 10 V — the 5V buck's ripple + transients can briefly exceed 10 V on cold start.
- [ ] **5.9** Solder C4 + C2 in PARALLEL across the ESP32 **VIN** and **GND** header pins. C4 polarity matters. Within **0.5"** of the header pins.
- [ ] **5.10** **Continuity gate:** ESP32 VIN → GND reads **open**.

> **Common mistakes:** F4 around only one wire — that's a differential-mode filter, but the ESP32 leg's worst noise is common-mode pickup from radiated ESC EMF. Solder joints >0.5" from ESP32 header pins — leads become inductors that kill HF filtering at the radio. Confusing P20 (this branch, 5V → ESP32) with P21 (next branch, Power Module → Pixhawk).

### §6 — Starlink Branch (F3 + C7 + C2)

- [ ] **6.1** Identify **P7** — 12 AWG RED (+) from ATO 7.5 A SB fuse to Starlink DC input.
- [ ] **6.2** Snap **F3 (13 mm clip-on)** around (+) wire only. Within **3"** of the **fuse block** (catch the noise near the source — the Starlink run is long).
- [ ] **6.3** Prep **C7 (100 µF / 35–50 V electrolytic)** + **C2 (100 nF ceramic)**.
- [ ] **6.4** Solder C7 + C2 in PARALLEL across the Starlink DC connector pigtail. C7 polarity matters. Within **1"** of the connector. Heat-shrink the joints.
- [ ] **6.5** **Continuity gate:** Starlink (+) → (−) at the plug reads **open**.

> **Common mistakes:** F3 placed at the Starlink end instead of the fuse end — Starlink has its own internal conditioning, so the goal is to prevent ESC noise from coupling onto the long P7 run, which means catching it at the source.

### §7 — BEC → Servo Branch (C6 + C2, no ferrite by design)

- [ ] **7.1** Prep **C6 (100 µF / 16–50 V electrolytic)** + **C2 (100 nF ceramic)**.
- [ ] **7.2** Solder C6 + C2 in PARALLEL across the (+) and (−) wires of the **P22** servo cable. **At the servo end**, not the BEC end (the servo is the inductive noise source; the cap absorbs there). C6 polarity matters. Within **1"** of the servo 3-pin connector.
- [ ] **7.3** Heat-shrink the junction.
- [ ] **7.4** **Continuity gate:** servo (+) → (−) reads **open**.

> No input ferrite on this branch by design.

### §8 — Sensor Signal Filtering (TDS critical, pH gated, 1-Wire optional)

> **WG-2 firmware reality:** pH path is **UART @ 9600 baud** per `firmware/main/sensor_bridge.c` even though the BOM (and parts of the JSON wiring spec) call it I²C. F5 BOJACK beads are **not installed up-front**. Do not cut and splice beads inline. If pool-test reveals UART framing errors with motor running, retrofit a single 13 mm clip-on on the CAT6 at the ESP32 end. Document and re-verify.

#### 8a. CRITICAL — TDS analog (S10)

- [ ] **8.1** Solder **C2 (100 nF ceramic)** between the ESP32 ADC pin reading TDS (S10) and ESP32 GND. **Within 0.25" of the ESP32 pin** — this is the strictest distance gate in the procedure. ADC accuracy depends on it.
- [ ] **8.2** Solder direct to header pin or breakout pad. Shortest possible leads.
- [ ] **8.3** **Continuity gate:** TDS pin → GND reads **open** (cap acts as open at DC).

#### 8b. SKIP up-front — pH UART (S8)

- [ ] **8.4** **DO NOT install F5 beads on pH lines.** Do not cut/splice the CAT6 pH pair. This step is intentionally a no-op at install time. Reassess after pool test (§troubleshooting).

#### 8c. OPTIONAL — 1-Wire DS18B20 (S9)

- [ ] **8.5** *(Optional, defer unless visible noise.)* Solder C2 (100 nF ceramic) between the ESP32 1-Wire data pin (S9) and GND, **<0.5" from the pin**.

#### 8d. DO NOT INSTALL — S7 IMU, S11 GPS

- [ ] **8.6** S7 (IMU) and S11 (GPS) are removed in WG-2 (replaced by Pixhawk built-in IMU and M8N GPS). Any beads or caps the BOM specified for these lines are **not needed** — skip entirely.

> **Common mistakes:** TDS cap landed on a long jumper to GND — that 1" of wire kills the filter. C2 must reach the ADC pin and the nearest GND pin in well under a quarter-inch.

### §9 — Copper Tape Shielding (DO LAST — after all filters installed and bench-verified)

Copper tape goes innermost (the conductive layer) → automotive self-adhesion tape (insulation, prevents shorts to neighbors) → split loom (mechanical protection). Drain wire grounded at **ONE end only** (source). Leave **0.5"** bare at connectors so the tape doesn't short to pins.

#### 9a. Cable-body wraps

- [ ] **9.1** **P20** (5V buck → ESP32, 22 AWG pair):
  - Wrap the cable body in copper tape. Slight overlap, no gaps.
  - Solder a **2"** drain pigtail (22–26 AWG) to the copper tape **at the 5V buck (source) end**.
  - Land the drain pigtail on the **5V buck GND** terminal.
  - Leave the ESP32 end of the tape **floating** (no drain).
  - Cover the entire copper tape run with automotive self-adhesion tape (SH2) so it can't short to neighbors.
- [ ] **9.2** **S1** (ESP32 UART → Pixhawk JST-SH 4-pin):
  - Same procedure as P20 but smaller cable.
  - Drain at the **ESP32 (source) end** → **ESP32 GND** at the breakout.
  - Pixhawk end floating.
- [ ] **9.3** **CAT6 sensor bundle** (S8/S9/S10): foil shield is built in. Verify the CAT6 foil drain is landed at **ESP32 GND only** (bow end floating). Should already be correct per the WG-2 wiring guide — verify, do not re-route.

> **P21 (Power Module → Pixhawk DF13)** does not need a cable-body wrap — it's short, runs adjacent to the Power Module's own enclosure, and the Power Module's internal filtering already attenuates the relevant frequencies. Skip.

#### 9b. Component-body wraps (WG-2 — all to (−) busbar, ONE end only)

For each component below, wrap the full body of the device in copper tape, then automotive self-adhesion tape over it. Solder a **1–2"** drain pigtail (22–26 AWG) from the copper tape surface to the **(−) busbar**. **One drain per body. Never daisy-chain drains.**

- [ ] **9.4** **ESC body** — replaces the original heat shrink. Avoid covering heatsink fins (don't thermally trap the ESC). Drain → (−) busbar.
- [ ] **9.5** **BEC body** (Castle). Drain → (−) busbar.
- [ ] **9.6** **12V buck converter body.** Drain → (−) busbar.
- [ ] **9.7** **5V buck converter body.** Drain → (−) busbar.
- [ ] **9.8** **5V Power Module body.** Drain → (−) busbar. (Yes, even though the Module has internal filtering — its switching converter still radiates, and a wrap+drain is cheap insurance against the Pixhawk compass picking it up.)

#### 9c. After every copper-tape install

- [ ] **9.9** Cover all copper tape with automotive self-adhesion tape (SH2). Bare copper tape near other wiring will short something at the worst possible time.
- [ ] **9.10** **Continuity check per shield:** drain wire → its destination GND = **closed** (through ground path). Drain wire → any (+) rail = **open**. If a drain reads continuity to (+), the tape is touching a (+) terminal somewhere — find and insulate it.

#### 9d. Do NOT wrap

- CAT6 bow sensor bundle (S8/S9/S10) — foil shield handles it.
- P5/P6 ESC-motor 8 AWG — noise source, not victim. F1 + C3 + C2 handle it.
- P17 3-phase ESC → motor wires — noise source. Split loom only.
- P1–P4 4 AWG trunk — short, fat, low impedance; not worth shielding.
- S7, S11 — sensors removed in WG-2.
- S10 TDS individually — already inside the CAT6 foil.

> **Common mistakes:** Drain at both ends → ground loop, makes things worse. No insulation over copper tape → drain shorts to a neighbor terminal. Daisy-chained drains → multiple component-body shields share one inductive return path, defeating the point.

### §10 — Aluminum Plate Shielding (referenced from WG-2; status: design only, parts on hand)

The grounded 12×24" aluminum mounting plate is a conductive shield between ESC (mounted underneath) and topside electronics (Jetson, Pixhawk, ESP32, converters, Power Module). **Status per WG-2: DESIGN ONLY, parts on hand, not yet implemented.** Bundled here because it's directly part of the EMI work; if you're skipping this section in the same install pass, mark §10 deferred and proceed to §11.

#### 10a. Plate prep (before mounting topside components)

- [ ] **10.1** Apply **Kapton tape** to the entire **top surface** of the aluminum plate. Double-layer wherever a ring terminal or bolt head will sit.
- [ ] **10.2** Install **dielectric thermal pads** under each converter footprint (12V buck, 5V buck, BEC, 5V Power Module).
- [ ] **10.3** Prep a **12 AWG BLK plate-ground jumper**: ring terminal → plate bolt at one end, the other end prepped for the (−) busbar.
- [ ] **10.4** Land the plate ground jumper on the **(−) busbar**. **Single point only — no second plate-to-ground anywhere on the boat.** A second tie = ground loop, kills the filtering scheme.

#### 10b. ESC under-plate mounting

- [ ] **10.5** Apply thermal pad to ESC underside. Mount ESC to the plate's **bottom surface** at the stern-ward end.
- [ ] **10.6** Drill/grommet a hole for the 8 AWG (P5/P6) power feed. Route through the grommet — wires must not contact bare plate edges.
- [ ] **10.7** Drill a separate small grommet hole for **S3 PWM** (Pixhawk → ESC). Route around plate edge or through this dedicated hole — keep separate from the 8 AWG power feed.
- [ ] **10.8** Conformal-coat the ESC PCB **OR** wrap the ESC body in closed-cell foam splash guard. ESC is now the lowest component in the hull and **will** see splash. Waterproofing is mandatory, not optional.

> **Critical rules (re-stated for emphasis):**
> - **Single ground point only** — no second plate-to-ground.
> - Kapton goes **under** every topside component. The plate is now live ground; a scraped trace or bare ring terminal edge = dead short.
> - ESC waterproofing is mandatory.

### §11 — Final Routing & Separation

- [ ] **11.1** Verify signal wires (22–26 AWG, CAT6) are physically routed **at least 12"** from 8 AWG motor power. Use opposite hull walls (signals starboard, power port — per the WG-2 wiring guide).
- [ ] **11.2** Confirm S3 PWM goes through its own grommet hole, not the 8 AWG hole.
- [ ] **11.3** Verify no copper tape edges contact unintended surfaces. Add SH2 patches anywhere a tape edge is close to a (+) terminal.
- [ ] **11.4** Tug-test every soldered joint. Re-zip-tie any cap that can swing.

---

## 5 — Post-Install Verification (V1–V6)

Do all six in order. Stop on the first failure; do not skip ahead.

- [ ] **V1. Visual inspection.** No loose solder, no pinched wires, all caps secured, no copper tape touching unintended surfaces. Polarity of every electrolytic visually re-checked.
- [ ] **V2. Full busbar continuity.** (+) → (−) on the busbar = **open (>1 MΩ)**. If shorted anywhere, stop and find it before re-energizing.
- [ ] **V3. Smoke test.** Reconnect battery at kill switch (insert MIDI 60 A, then MRBF **last**). Look for smoke. (Yes, really.)
- [ ] **V4. Per-rail voltage.** Multimeter at each branch output:
  - Busbar = **22–26 V** (depending on demo vs production battery state).
  - 5V Power Module output to Pixhawk POWER (P21) = **5.0 ± 0.1 V**.
  - 12V buck output to Jetson + fan (P18 / P19) = **12.0 ± 0.2 V**.
  - 5V buck output to ESP32 (P20) = **5.0 ± 0.1 V**.
  - BEC output (P22) = per BEC spec (typically 5.5 V or 6 V).

- [ ] **V5. Motor spin-up.** Power on motor briefly with **prop removed**, low throttle. No smoke, no abnormal buzz, no rail sag >0.5 V on any branch.
- [ ] **V6. Compass-drift gate.** Open QGC, watch heading. With motor OFF: heading is stable. With motor running at low throttle: heading shifts **<2°** from static value. **>5° shift = EMI is still a problem** — re-inspect §2 (ESC branch) and §10 plate ground.

---

## 6 — Update Docs After Install (deferred — track but not in scope today)

- Update `AQUABOTS_EMI_FILTERING_BOM.pdf` status column (ORDER → INSTALLED). Deferred — BOM Rev ISR-5 regen is a separate task.
- Update `AQUABOTS_POWER_SYSTEM_CHANGELOG.md` with install date and append Rev ISR-5 block.
- Bump `AQUABOTS_WIRING_GUIDE.md` WG-2 → WG-3 with summary: "EMI filtering installed on the WG-2 topology. Production DSServo + new BEC wired. Compass + accel recalibrated post-install." (Note: do NOT re-introduce the FAR-1 architecture — that was a paper-only proposal that was never installed.)
- Record SERVO1 calibration values (MIN/MAX/TRIM/REVERSED) in the wiring guide or a new `PIXHAWK_SERVO_CONFIG.md`.

---

## 7 — Known Deviations from BOM Rev ISR-4b (under WG-2)

| BOM Rev ISR-4b says                                  | This procedure does                                                              | Reason |
|------------------------------------------------------|----------------------------------------------------------------------------------|--------|
| 4 ferrite beads on I²C (2 pH SDA + 2 SCL) + 2 optional UART | **0 F5 beads up-front.** Pool-test-gated CAT6 clip-on only.            | Per `firmware/main/sensor_bridge.c`, pH is UART @ 9600 baud. I²C beads not needed. |
| 2 ferrite beads on IMU SDA/SCL                       | **0** — sensor removed.                                                          | S7 IMU removed in WG-2. Pixhawk built-in IMU. |
| Copper tape on P21 (5V → ESP32 in BOM era), S10 individual, optional S1/S2 | **P20** (5V buck → ESP32; same target, the wire ID was P21 in BOM era and is P20 in WG-2) + S1 + ESC body + BEC body + 12V buck body + 5V buck body + **5V Power Module body**. | Wire-ID renumbering between BOM era and WG-2. WG-2 added component-body wraps for radiated emission, including the Power Module. CAT6 foil already shields S10, so individual wrap removed. |
| C4 = 10 µF / 10 V+ on ESP32 VIN                      | **C4 = 100 µF / 16 V+** electrolytic.                                            | 5V buck cold-start can transient near 10 V; 16 V rating gives margin. 100 µF gives meaningful ride-through and bulk that 10 µF does not at this load. |
| F4 location: "5V Buck output to ESP32"               | **F4 on P20 (5V Buck output to ESP32 pair).**                                    | Same target — wire ID renumbered from P21 (BOM era) to P20 (WG-2). F4 still common-mode (both wires through the ferrite together). |
| 5V Power Module on Pixhawk POWER (no BOM line for additional caps) | **No added caps on this branch.** Power Module has internal filtering — that's why the BOM doesn't list any. **This procedure agrees with BOM here** — the FAR-1 paper change that added C5b 47 µF was never built. | (No deviation — listed for clarity because earlier drafts of this procedure had a FAR-1-flavored C5b that doesn't belong.) |
| C2 ceramic qty "10+"                                 | ~8 used (~10 with optional 1-Wire and spares). BOM qty is sufficient.            | Qty unchanged in spirit; reflects actual install (no C5b means one fewer C2 vs FAR-1). |

These deviations feed into BOM Rev ISR-5 regeneration (separate task, not in scope for this install).

---

## 8 — Troubleshooting & Fallback

If V1–V6 fail, follow this triage tree before reaching for a different design.

| Symptom                                            | First place to check                                       | Mitigation                                                                                          |
|----------------------------------------------------|------------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| **V2 fails — busbar shorted**                      | C1 polarity reversed, or stray wire strand across studs.   | Disconnect C1, re-test. If now open, C1 was reversed; replace.                                      |
| **V3 fails — smoke / smell on power-up**           | Reversed electrolytic somewhere; or copper tape shorting.  | Kill power. Identify which converter is hot. Inspect every electrolytic in that branch. Re-check copper-tape insulation per §9c. |
| **V4 fails — Pixhawk 5 V rail low (<4.9 V)**       | Power Module faulty / busbar sag during inrush.            | Check busbar voltage at the Power Module input (P9). If busbar is sagging too, look at C1 and trunk torque. If busbar is fine but Pixhawk rail is low, replace the Power Module. |
| **V4 fails — ESP32 5 V rail low**                  | F2 wired around both wires (= common-mode, wrong here).    | Re-do §5a with F2 around (+) only.                                                                  |
| **V5 fails — Pixhawk reset on ESC arm/calibration** | Brownout: Power Module or upstream sagging during inrush. | Check busbar sag; check Power Module spec vs Pixhawk peak load. Adding a Schottky + small bulk cap upstream of the Power Module input is a last-resort retrofit; do NOT add bulk at the DF13 connector itself. |
| **V5 fails — abnormal motor buzz**                 | F1 not single-pass (multi-turn = saturated core).          | Re-do F1 as single pass.                                                                            |
| **V6 fails — compass drift >5° with motor on**     | ESC body not shielded; F1 too far from ESC; copper-tape drain bonded at wrong end. | Re-verify §2.3 (F1 within 2"), §9.4 (ESC body wrapped, drain to (−) busbar at one end), §10.4 (plate ground = single point). |
| **Pool test — pH UART framing errors with motor on** | Conducted noise on CAT6.                                 | Add **one** 13 mm clip-on ferrite on the CAT6 bundle at the ESP32 end. Do **not** cut/splice F5 beads inline. Document and re-run V6. |
| **Pool test — TDS reading noisy with motor on**    | C2 at ADC pin too far from pin, or missing.                | Re-solder C2 to <0.25" from the ADC pin. If still noisy after that, add a clip-on ferrite on the CAT6 at the ESP32 end (same retrofit as pH). |
| **Compass drift fixed by detaching plate ground**  | Ground loop — second plate-to-ground tie somewhere.        | Find the second tie. Per §10.4 only **one** plate-to-(−)-busbar connection.                         |

### Optional pool-test-gated additions (only if symptoms appear)

- CAT6 clip-on ferrite at ESP32 end — for pH UART or TDS noise (one ferrite covers both since they share the bundle).
- Schottky + small bulk cap upstream of Power Module input — for inrush-induced Pixhawk brownout. Last resort.
- Cable-body wrap on S2 (Pixhawk TELEM2 → Jetson) — if Jetson telemetry shows MAVLink errors with motor running.

---

## 9 — Do-Not-Do List (re-stated)

- Do **NOT** energize anything until **all** §-end continuity gates pass.
- Do **NOT** ground both ends of any shield. Source end only.
- Do **NOT** multi-turn the F1 toroid. Single pass only.
- Do **NOT** swap F4 from common-mode (both wires) to single-wire. Topology is intentional.
- Do **NOT** skip the 100 nF ceramic in any parallel pair. Electrolytic alone covers low-frequency only.
- Do **NOT** cut and splice F5 beads inline on pH SDA/SCL — pH is UART, not I²C.
- Do **NOT** add caps at the Pixhawk POWER DF13 (no C5b). The dedicated Power Module already filters this rail; bulk at the DF13 risks oscillation against the Module's regulation loop.
- Do **NOT** route the ESP32 off the 12V buck. Under WG-2 the ESP32 has its own 5V buck via P13/P14/P20. Routing ESP32 off the 12V rail is the FAR-1 paper architecture, which was never installed.
- Do **NOT** add a second plate-to-ground tie — single point only or the whole filtering scheme falls apart.

---

*Companion documents (still authoritative for their domains):*

- `AQUABOTS_WIRING_GUIDE.md` Rev WG-2 — wire IDs, connector pinouts, rail layout, routing.
- `AQUABOTS_EMI_FILTERING_BOM.pdf` Rev ISR-4b — parts catalog (with deviations per §7 above).
- `AQUABOTS_POWER_SYSTEM_CHANGELOG.md` — full revision history (FAR-1 entry walked back; current state is WG-2).

*Predecessor docs (stubbed, do not reference):*

- `AQUABOTS_EMI_INSTALL_GUIDE.md` (WG-3 / FAR-1 era) — merged into this procedure and reverted to WG-2 alignment.
- `field-procedures/EMI_FILTERING_INSTALL_CHECKLIST.md` (FAR-1 patched) — merged into this procedure.
